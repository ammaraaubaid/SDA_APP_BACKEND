from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, APIRouter
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from database import get_db
from models import User, Follow, Post, PostImage,PostLike
from schema import TokenPair, UserCreate, UserLogin, UserUpdate
from database import engine, Base, SessionLocal
import uuid
import os
import shutil
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Serve uploaded files as static ──────────────────────
os.makedirs("uploads", exist_ok=True)
# app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# --- Config ---
SECRET_KEY = "fbab35ec4019c91b7d06cd19a0e7290ca81d7b6bed0ea43e1fdcfa7128e7c1f2"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

import bcrypt

def hash_password(password: str):
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_password.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str):
    password_byte_enc = plain_password.encode('utf-8')
    hashed_password_byte_enc = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_byte_enc, hashed_password_byte_enc)


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


Base.metadata.create_all(bind=engine)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


# ── AUTH ─────────────────────────────────────────────────

@app.post("/signup")
def signup(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    hashed_password = hash_password(user.password)
    new_user = User(
        id=str(uuid.uuid4()),
        username=user.username,
        email=user.email,
        password=hashed_password,
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
        print(f"Database Error: {e}")
        raise HTTPException(status_code=500, detail="Database insertion failed")

    return {"message": "User created successfully"}


# @app.post("/login", response_model=TokenPair)
# def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    
#     db_user = db.query(User).filter(User.username == form_data.username).first()

#     if not db_user or not verify_password(form_data.password, db_user.password):
#         raise HTTPException(status_code=401, detail="Invalid username or password")

#     access_token = create_access_token(data={"sub": db_user.id})
#     refresh_token = create_access_token(
#         data={"sub": db_user.id},
#         expires_delta=timedelta(days=7)
#     )

#     return {
#         "access_token": access_token,
#         "refresh_token": refresh_token,
#         "token_type": "bearer"
#     }



from fastapi import Form

@app.post("/login", response_model=TokenPair)
def login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    db_user = db.query(User).filter(User.username == username).first()

    if not db_user or not verify_password(password, db_user.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    access_token = create_access_token(data={"sub": db_user.id})
    refresh_token = create_access_token(
        data={"sub": db_user.id},
        expires_delta=timedelta(days=7)
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@app.post("/refresh", response_model=TokenPair)
def refresh_token(refresh_token: str, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    new_access_token = create_access_token(data={"sub": user.id})

    return {
        "access_token": new_access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


# ── USERS ─────────────────────────────────────────────────

@app.get("/users/id/{user_id}")
def get_user_by_id(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# @app.get("/users/{user_id}/posts")
# def get_user_posts(user_id: str, db: Session = Depends(get_db)):
#     posts = db.query(Post).filter(Post.author_id == user_id).all()
#     return posts



@app.get("/users/{user_id}/posts")
def get_user_posts(user_id: str, db: Session = Depends(get_db)):
    posts = db.query(Post).filter(Post.author_id == user_id).all()

    result = []

    for post in posts:
        images = db.query(PostImage).filter(PostImage.post_id == post.id).all()

        result.append({
            "id": post.id,
            "content": post.content,
            "created_at": post.created_at,
            "images": [
                {
                    "id": img.id,
                    "image_url": img.image_url
                }
                for img in images
            ]
        })

    return result

# ── UPDATE PROFILE ────────────────────────────────────────
# Called by edit.tsx when user taps "Done"
@app.patch("/users/{user_id}")
def update_user(
    user_id: str,
    updates: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Only allow users to update their own profile
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not allowed to edit another user's profile")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check username uniqueness if it's being changed
    if updates.username and updates.username != user.username:
        taken = db.query(User).filter(User.username == updates.username).first()
        if taken:
            raise HTTPException(status_code=400, detail="Username already taken")

    # Apply only the fields that were actually sent (not None)
    if updates.full_name is not None:
        user.full_name = updates.full_name
    if updates.username is not None:
        user.username = updates.username
    if updates.bio is not None:
        user.bio = updates.bio
    if updates.department is not None:
        user.department = updates.department
    if updates.university is not None:
        user.university = updates.university

    db.commit()
    db.refresh(user)

    return {"message": "Profile updated", "user": {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "bio": user.bio,
        "department": user.department,
        "university": user.university,
        "profile_pic": user.profile_pic,
    }}



PROFILE_PIC_DIR = "uploads/user_profile"
os.makedirs(PROFILE_PIC_DIR, exist_ok=True)


@app.post("/users/{user_id}/upload-profile-pic")
async def upload_profile_pic(
    user_id: str, 
    file: UploadFile = File(...), 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Security Check: Only the owner can change their photo
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this profile")

    # 2. Validate it's actually an image
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image (jpg, png, etc.)")

    # 3. Create a unique filename to prevent cache issues and collisions
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    filename = f"{uuid.uuid4()}.{ext}"
    file_path = os.path.join(PROFILE_PIC_DIR, filename)

    # 4. Save the file to the 'uploads/user_profile' folder
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not save file")

    # 5. Store the PUBLIC URL in the database
    # This matches your app.mount("/uploads", StaticFiles...) setting
    public_url = f"/uploads/user_profile/{filename}"
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.profile_pic = public_url
    db.commit()
    db.refresh(user)

    return {
        "message": "Profile picture updated successfully",
        "profile_pic": public_url
    }

# ── UPLOAD PROFILE PICTURE ────────────────────────────────
# Called by edit.tsx after the text fields are saved, if user picked a new photo

# ── GET USER BY USERNAME ──────────────────────────────────
@app.get("/users/username/{username}")
def get_user_by_username(username: str, db: Session = Depends(get_db)):
    # Query the database for the user with this specific username
    user = db.query(User).filter(User.username == username).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Return the ID and other public info
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "profile_pic": user.profile_pic
    }
# ── FOLLOW ────────────────────────────────────────────────

@app.post("/follow/{user_id}")
def follow_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="You cannot follow yourself")

    existing = db.query(Follow).filter(
        Follow.follower_id == current_user.id,
        Follow.following_id == user_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Already following")

    new_follow = Follow(
        id=str(uuid.uuid4()),
        follower_id=current_user.id,
        following_id=user_id
    )

    db.add(new_follow)
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
        Follow.following_id == user_id
    ).first()

    if not follow:
        raise HTTPException(status_code=404, detail="Not following")

    db.delete(follow)
    db.commit()

    return {"message": "Unfollowed successfully"}

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
# ── FOLLOWERS / FOLLOWING ─────────────────────────────────

@app.get("/users/{user_id}/followers")
def get_followers(user_id: str, db: Session = Depends(get_db)):
    followers = db.query(Follow).filter(Follow.following_id == user_id).all()
    return [{"follower_id": f.follower_id, "following_id": f.following_id} for f in followers]


@app.get("/users/{user_id}/following")
def get_following(user_id: str, db: Session = Depends(get_db)):
    following = db.query(Follow).filter(Follow.follower_id == user_id).all()
    return [{"follower_id": f.follower_id, "following_id": f.following_id} for f in following]

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# 1. Define the directory
PROFILE_PIC_DIR = "uploads/user_profile"
os.makedirs(PROFILE_PIC_DIR, exist_ok=True)

# 2. Use @app.post directly (or ensure router is included)
# @app.post("/users/{user_id}/upload-profile-pic")
# async def upload_profile_pic(
#     user_id: str, 
#     file: UploadFile = File(...), 
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user) # Ensures security
# ):
#     # Security: Ensure user is only updating their own pic
#     if current_user.id != user_id:
#         raise HTTPException(status_code=403, detail="Not authorized")

#     # Validate file type
#     if not file.content_type.startswith("image/"):
#         raise HTTPException(status_code=400, detail="File must be an image")

#     # Generate unique filename to avoid browser caching issues
#     ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
#     filename = f"{uuid.uuid4()}.{ext}"
#     file_path = os.path.join(PROFILE_PIC_DIR, filename)

#     # Save to disk
#     with open(file_path, "wb") as buffer:
#         shutil.copyfileobj(file.file, buffer)

#     # Save the WEB URL to the database (so your frontend can see it)
#     public_url = f"/uploads/user_profile/{filename}"
    
#     user = db.query(User).filter(User.id == user_id).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     user.profile_pic = public_url
#     db.commit()

#     return {
#         "message": "Profile picture updated",
#         "profile_pic": public_url
#     }

# ── POSTS ─────────────────────────────────────────────────

@app.post("/posts")
async def create_post(
    content: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Create post first
    new_post = Post(
        id=str(uuid.uuid4()),
        author_id=current_user.id,
        content=content
    )

    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    # Create folder

    image_urls = []

    for file in files:
        # Validate image
        if not file.content_type.startswith("image/"):
            continue

        ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
        filename = f"{uuid.uuid4()}.{ext}"
        filepath = f"uploads/posts/{filename}"

        # Save file
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Save image in DB
        image = PostImage(
            id=str(uuid.uuid4()),
            post_id=new_post.id,
            image_url=f"/uploads/posts/{filename}"
        )

        db.add(image)
        image_urls.append(image.image_url)

    db.commit()

    return {
        "message": "Post created",
        "post_id": new_post.id,
        "images": image_urls
    }
    
    
@app.post("/posts/{post_id}/like")
def like_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    existing = db.query(PostLike).filter(
        PostLike.post_id == post_id,
        PostLike.user_id == current_user.id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Already liked")

    like = PostLike(
        id=str(uuid.uuid4()),
        post_id=post_id,
        user_id=current_user.id
    )

    db.add(like)
    db.commit()

    return {"message": "Post liked"}
router = APIRouter()

@app.delete("/posts/{post_id}/like")
def unlike_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    like = db.query(PostLike).filter(
        PostLike.post_id == post_id,
        PostLike.user_id == current_user.id
    ).first()

    if not like:
        raise HTTPException(status_code=404, detail="Not liked yet")

    db.delete(like)
    db.commit()

    return {"message": "Unliked"}


@app.delete("/posts/{post_id}/like")
def unlike_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    like = db.query(PostLike).filter(
        PostLike.post_id == post_id,
        PostLike.user_id == current_user.id
    ).first()

    if not like:
        raise HTTPException(status_code=404, detail="Not liked yet")

    db.delete(like)
    db.commit()

    return {"message": "Unliked"}



@app.get("/posts/{post_id}/likes")
def get_likes(post_id: str, db: Session = Depends(get_db)):
    count = db.query(PostLike).filter(PostLike.post_id == post_id).count()
    return {"post_id": post_id, "likes": count}

from models import Comment
from schema import CommentCreate

# ================= CREATE POST =================
@app.post("/post-with-image")
def create_post(
    author_id: str = Form(...),
    content: str = Form(...),
    file: UploadFile = File(None),
    db: Session = Depends(get_db)
):

    print("AUTHOR:", author_id)
    print("CONTENT:", content)
    print("FILE:", file.filename if file else "NO FILE")

    image_url = None

    # ================= SAVE IMAGE =================
    if file and file.filename:
        filename = f"{uuid.uuid4()}_{file.filename}"
        path = f"uploads/{filename}"

        with open(path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        image_url = f"/uploads/{filename}"

    # ================= SAVE POST =================
    post = Post(
        id=str(uuid.uuid4()),
        author_id=author_id,
        content=content,
        image=image_url,
        created_at=datetime.utcnow()
    )

    db.add(post)
    db.commit()
    db.refresh(post)

    return {"message": "post created"}



@app.post("/posts/{post_id}/comment")
def create_comment(
    post_id: str,
    comment: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    new_comment = Comment(
        id=str(uuid.uuid4()),
        post_id=post_id,
        author_id=current_user.id,
        content=comment.content,
        parent_id=comment.parent_id
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
            "created_at": new_comment.created_at
        }
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
            "created_at": c.created_at
        }
        for c in comments
    ]

@app.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    if comment.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    db.delete(comment)
    db.commit()

    return {"message": "Comment deleted"}



UPLOAD_DIR = "uploads/user_profile"
os.makedirs(UPLOAD_DIR, exist_ok=True)
# @app.post("/users/{user_id}/profile-pic")
# async def upload_profile_pic(
#     user_id: str,
#     file: UploadFile = File(...),
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     if current_user.id != user_id:
#         raise HTTPException(status_code=403, detail="Not allowed")

#     user = db.query(User).filter(User.id == user_id).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     # ✅ Ensure folder exists
#     upload_dir = "uploads/user_profile"
#     os.makedirs(upload_dir, exist_ok=True)

#     # ✅ Validate image
#     if not file.content_type.startswith("image/"):
#         raise HTTPException(status_code=400, detail="Only images allowed")

#     # ✅ Unique filename (better than overwriting)
#     ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
#     filename = f"{uuid.uuid4()}.{ext}"

#     filepath = os.path.join(upload_dir, filename)

#     # ✅ Save file
#     with open(filepath, "wb") as buffer:
#         shutil.copyfileobj(file.file, buffer)

#     # ✅ Store PUBLIC URL (not raw path)
#     public_url = f"/uploads/user_profile/{filename}"
#     user.profile_pic = public_url

#     db.commit()
#     db.refresh(user)

#     return {
#         "message": "Profile picture updated",
#         "profile_pic": public_url
#     }

# app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# @router.post("/upload-profile-pic/{user_id}")
# def upload_profile_pic(user_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    
#     # Ensure folder exists
#     os.makedirs(UPLOAD_DIR, exist_ok=True)

#     # Create unique filename
#     file_ext = file.filename.split(".")[-1]
#     file_name = f"user_{user_id}.{file_ext}"
#     file_path = os.path.join(UPLOAD_DIR, file_name)

#     # Save file
#     with open(file_path, "wb") as buffer:
#         shutil.copyfileobj(file.file, buffer)

#     # Save path in DB
#     user = db.query(User).filter(User.id == user_id).first()
#     user.profile_pic = file_path
#     db.commit()

#     return {
#         "message": "Profile picture updated",
#         "file_path": file_path
#     }
    
from fastapi.staticfiles import StaticFiles
