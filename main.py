import os
import uuid
import shutil

import bcrypt
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from jose import JWTError, jwt

from database import get_db, engine, Base
from models import User, Follow, Post, PostImage, PostLike, Comment
from schema import TokenPair, UserCreate, UserUpdate, CommentCreate


# ── App & Middleware ──────────────────────────────────────

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static Files & Upload Dirs ────────────────────────────

os.makedirs("uploads/user_profile", exist_ok=True)
os.makedirs("uploads/posts", exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ── DB Init ───────────────────────────────────────────────

Base.metadata.create_all(bind=engine)

# ── Config ────────────────────────────────────────────────

SECRET_KEY = "fbab35ec4019c91b7d06cd19a0e7290ca81d7b6bed0ea43e1fdcfa7128e7c1f2"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

# ── Auth Helpers ──────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


# ── AUTH ──────────────────────────────────────────────────

@app.post("/signup")
def signup(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=400, detail="User already exists")

    new_user = User(
        id=str(uuid.uuid4()),
        username=user.username,
        email=user.email,
        password=hash_password(user.password),
        full_name=user.full_name,
        university=user.university,
        department=user.department,
        bio=user.bio,
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database insertion failed")

    return {"message": "User created successfully"}


@app.post("/login", response_model=TokenPair)
def login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    db_user = db.query(User).filter(User.username == username).first()

    if not db_user or not verify_password(password, db_user.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    access_token = create_access_token(data={"sub": db_user.id})
    refresh_token = create_access_token(data={"sub": db_user.id}, expires_delta=timedelta(days=7))

    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@app.post("/refresh", response_model=TokenPair)
def refresh_token(refresh_token: str, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "access_token": create_access_token(data={"sub": user.id}),
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


# ── USERS ─────────────────────────────────────────────────

@app.get("/users/id/{user_id}")
def get_user_by_id(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.get("/users/username/{username}")
def get_user_by_username(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "profile_pic": user.profile_pic,
    }


@app.patch("/users/{user_id}")
def update_user(
    user_id: str,
    updates: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not allowed to edit another user's profile")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if updates.username and updates.username != user.username:
        if db.query(User).filter(User.username == updates.username).first():
            raise HTTPException(status_code=400, detail="Username already taken")

    for field in ("full_name", "username", "bio", "department", "university"):
        value = getattr(updates, field, None)
        if value is not None:
            setattr(user, field, value)

    db.commit()
    db.refresh(user)

    return {
        "message": "Profile updated",
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "bio": user.bio,
            "department": user.department,
            "university": user.university,
            "profile_pic": user.profile_pic,
        },
    }


@app.post("/users/{user_id}/upload-profile-pic")
async def upload_profile_pic(
    user_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this profile")

    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image (jpg, png, etc.)")

    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    filename = f"{uuid.uuid4()}.{ext}"
    file_path = os.path.join("uploads/user_profile", filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not save file")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.profile_pic = f"/uploads/user_profile/{filename}"
    db.commit()
    db.refresh(user)

    return {"message": "Profile picture updated successfully", "profile_pic": user.profile_pic}


@app.get("/users/{user_id}/posts")
def get_user_posts(user_id: str, db: Session = Depends(get_db)):
    posts = db.query(Post).filter(Post.author_id == user_id).all()

    return [
        {
            "id": post.id,
            "content": post.content,
            "created_at": post.created_at,
            "images": [
                {"id": img.id, "image_url": img.image_url}
                for img in db.query(PostImage).filter(PostImage.post_id == post.id).all()
            ],
        }
        for post in posts
    ]


# ── FOLLOW ────────────────────────────────────────────────

@app.post("/follow/{user_id}")
def follow_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="You cannot follow yourself")

    if db.query(Follow).filter(Follow.follower_id == current_user.id, Follow.following_id == user_id).first():
        raise HTTPException(status_code=400, detail="Already following")

    db.add(Follow(id=str(uuid.uuid4()), follower_id=current_user.id, following_id=user_id))
    db.commit()

    return {"message": "Followed successfully"}


@app.delete("/unfollow/{user_id}")
def unfollow_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    follow = db.query(Follow).filter(
        Follow.follower_id == current_user.id,
        Follow.following_id == user_id,
    ).first()

    if not follow:
        raise HTTPException(status_code=404, detail="Not following")

    db.delete(follow)
    db.commit()

    return {"message": "Unfollowed successfully"}


@app.get("/users/{user_id}/followers")
def get_followers(user_id: str, db: Session = Depends(get_db)):
    followers = db.query(Follow).filter(Follow.following_id == user_id).all()
    return [{"follower_id": f.follower_id, "following_id": f.following_id} for f in followers]


@app.get("/users/{user_id}/following")
def get_following(user_id: str, db: Session = Depends(get_db)):
    following = db.query(Follow).filter(Follow.follower_id == user_id).all()
    return [{"follower_id": f.follower_id, "following_id": f.following_id} for f in following]


# ── POSTS ─────────────────────────────────────────────────

@app.post("/posts")
async def create_post(
    content: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    new_post = Post(id=str(uuid.uuid4()), author_id=current_user.id, content=content)
    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    image_urls = []
    for file in files:
        if not file.content_type.startswith("image/"):
            continue

        ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
        filename = f"{uuid.uuid4()}.{ext}"
        filepath = f"uploads/posts/{filename}"

        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        image = PostImage(id=str(uuid.uuid4()), post_id=new_post.id, image_url=f"/uploads/posts/{filename}")
        db.add(image)
        image_urls.append(image.image_url)

    db.commit()

    return {"message": "Post created", "post_id": new_post.id, "images": image_urls}


@app.post("/posts/{post_id}/like")
def like_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if db.query(PostLike).filter(PostLike.post_id == post_id, PostLike.user_id == current_user.id).first():
        raise HTTPException(status_code=400, detail="Already liked")

    db.add(PostLike(id=str(uuid.uuid4()), post_id=post_id, user_id=current_user.id))
    db.commit()

    return {"message": "Post liked"}


@app.delete("/posts/{post_id}/like")
def unlike_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    like = db.query(PostLike).filter(PostLike.post_id == post_id, PostLike.user_id == current_user.id).first()
    if not like:
        raise HTTPException(status_code=404, detail="Not liked yet")

    db.delete(like)
    db.commit()

    return {"message": "Unliked"}


@app.get("/posts/{post_id}/likes")
def get_likes(post_id: str, db: Session = Depends(get_db)):
    count = db.query(PostLike).filter(PostLike.post_id == post_id).count()
    return {"post_id": post_id, "likes": count}


# ── COMMENTS ─────────────────────────────────────────────

@app.post("/posts/{post_id}/comment")
def create_comment(
    post_id: str,
    comment: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    new_comment = Comment(
        id=str(uuid.uuid4()),
        post_id=post_id,
        author_id=current_user.id,
        content=comment.content,
        parent_id=comment.parent_id,
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)

    return {
        "message": "Comment added",
        "comment": {
            "id": new_comment.id,
            "content": new_comment.content,
            "post_id": new_comment.post_id,
            "author_id": new_comment.author_id,
            "parent_id": new_comment.parent_id,
            "created_at": new_comment.created_at,
        },
    }


@app.get("/posts/{post_id}/comments")
def get_comments(post_id: str, db: Session = Depends(get_db)):
    comments = db.query(Comment).filter(Comment.post_id == post_id).all()
    return [
        {
            "id": c.id,
            "content": c.content,
            "author_id": c.author_id,
            "parent_id": c.parent_id,
            "created_at": c.created_at,
        }
        for c in comments
    ]


@app.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    if comment.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    db.delete(comment)
    db.commit()

    return {"message": "Comment deleted"}