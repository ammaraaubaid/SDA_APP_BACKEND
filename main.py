import os
import uuid
import shutil
from schema import MessageUpdate
import bcrypt
from datetime import datetime, timedelta
from sqlalchemy import or_
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from fastapi.responses import HTMLResponse
import re
from sqlalchemy import text

from models import (
    User, Follow, Post, PostImage, PostLike, Comment,
    Conversation, ConversationParticipant, Message
)
from database import get_db, engine, Base
from schema import TokenPair, UserCreate, UserUpdate, CommentCreate, MessageUpdate

# ── DB Init ───────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

# ── Config ────────────────────────────────────────────────
SECRET_KEY = "fbab35ec4019c91b7d06cd19a0e7290ca81d7b6bed0ea43e1fdcfa7128e7c1f2"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
BASE_URL = "https://sda-app-backend.onrender.com"  # ← your backend URL

# ── Email Config ──────────────────────────────────────────
mail_config = ConnectionConfig(
    MAIL_USERNAME="unifisocialnetworkingapp@gmail.com",        # ← your Gmail
    MAIL_PASSWORD="btla ldzd gsef mpcp",         # ← Gmail App Password
    MAIL_FROM="unifisocialnetworkingapp@gmail.com",            # ← same Gmail
    MAIL_FROM_NAME="NU Connect",
    MAIL_PORT=587,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
)
fastmail = FastMail(mail_config)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads/user_profile", exist_ok=True)
os.makedirs("uploads/posts", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

NU_EMAIL_REGEX = re.compile(r'^l\d{6}@lhr\.nu\.edu\.pk$', re.IGNORECASE)

# ── Helpers ───────────────────────────────────────────────

def validate_nu_email_format(email: str) -> None:
    if not NU_EMAIL_REGEX.match(email):
        raise HTTPException(
            status_code=400,
            detail="Email must be in the format lXXXXXX@lhr.nu.edu.pk"
        )

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

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

def create_verification_token(email: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=24)
    return jwt.encode({"sub": email, "exp": expire, "type": "verify"}, SECRET_KEY, algorithm=ALGORITHM)

def decode_verification_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "verify":
            return None
        return payload.get("sub")
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
async def signup(user: UserCreate, db: Session = Depends(get_db)):
    validate_nu_email_format(user.email)

    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")

    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        id=str(uuid.uuid4()),
        username=user.username,
        email=user.email,
        password=hash_password(user.password),
        full_name=user.full_name,
        university=user.university,
        department=user.department,
        bio=user.bio,
        verified=False,          # ← starts unverified
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database insertion failed")

    # Send verification email
    token = create_verification_token(new_user.email)
    verify_link = f"{BASE_URL}/verify-email?token={token}"

    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: auto; padding: 30px; border-radius: 10px; background: #f9f9f9;">
        <h2 style="color: #007AFF;">Welcome to NU Connect! 👋</h2>
        <p>Hi <b>{new_user.username}</b>, thanks for signing up.</p>
        <p>Please verify your email address by clicking the button below:</p>
        <a href="{verify_link}" 
           style="display: inline-block; padding: 12px 24px; background: #007AFF; color: white; 
                  border-radius: 8px; text-decoration: none; font-weight: bold; margin: 16px 0;">
            Verify Email
        </a>
        <p style="color: #888; font-size: 13px;">This link expires in 24 hours.</p>
        <p style="color: #888; font-size: 13px;">If you didn't sign up, ignore this email.</p>
    </div>
    """

    message = MessageSchema(
        subject="Verify your NU Connect account",
        recipients=[new_user.email],
        body=html_body,
        subtype=MessageType.html,
    )

    try:
        await fastmail.send_message(message)
    except Exception as e:
        print(f"Email sending failed: {e}")
        # Don't block signup if email fails, just log it

    return {"message": "Account created! Please check your email to verify your account."}


@app.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    email = decode_verification_token(token)

    if not email:
        return HTMLResponse("""
            <h2 style="color:red; font-family:Arial">❌ Invalid or expired link.</h2>
            <p>Please sign up again or request a new verification email.</p>
        """)

    user = db.query(User).filter(User.email == email).first()
    if not user:
        return HTMLResponse("<h2>User not found.</h2>")

    if user.verified:
        return HTMLResponse("""
            <h2 style="font-family:Arial">✅ Already verified!</h2>
            <p>You can log in to NU Connect.</p>
        """)

    user.verified = True
    db.commit()

    return HTMLResponse("""
        <div style="font-family:Arial; text-align:center; padding:40px;">
            <h2 style="color:#007AFF">✅ Email Verified!</h2>
            <p>Your account is now active. You can now log in to <b>NU Connect</b>.</p>
        </div>
    """)


@app.post("/resend-verification")
async def resend_verification(email: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="No account with this email")

    if user.verified:
        raise HTTPException(status_code=400, detail="Email already verified")

    token = create_verification_token(user.email)
    verify_link = f"{BASE_URL}/verify-email?token={token}"

    html_body = f"""
    <div style="font-family: Arial, sans-serif; padding: 30px;">
        <h2 style="color: #007AFF;">Verify your NU Connect account</h2>
        <p>Click below to verify your email:</p>
        <a href="{verify_link}" style="padding: 12px 24px; background: #007AFF; color: white; border-radius: 8px; text-decoration: none;">
            Verify Email
        </a>
        <p style="color: #888; font-size: 13px;">Expires in 24 hours.</p>
    </div>
    """

    message = MessageSchema(
        subject="Verify your NU Connect account",
        recipients=[user.email],
        body=html_body,
        subtype=MessageType.html,
    )
    await fastmail.send_message(message)

    return {"message": "Verification email resent"}


@app.post("/login", response_model=TokenPair)
def login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    db_user = db.query(User).filter(User.username == username).first()
    if not db_user or not verify_password(password, db_user.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # ← Block unverified users
    if not db_user.verified:
        raise HTTPException(
            status_code=403,
            detail="Please verify your email before logging in. Check your inbox."
        )

    access_token = create_access_token(data={"sub": db_user.id})
    refresh_token = create_access_token(data={"sub": db_user.id}, expires_delta=timedelta(days=7))

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user_id": db_user.id,
    }
    
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


# ✅ FIXED: now saves PostImage row so images appear in /users/{id}/posts
@app.post("/post-with-image")
def create_post_with_image(
    content: str = Form(...),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # ✅ now uses real auth, not raw author_id
):
    try:
        # 1. Create the Post row first
        post = Post(
            id=str(uuid.uuid4()),
            author_id=current_user.id,  # ✅ from token, not form
            content=content,
            created_at=datetime.utcnow(),
        )
        db.add(post)
        db.commit()
        db.refresh(post)

        # 2. If an image was uploaded, save file AND create PostImage row
        image_url = None
        if file and file.filename:
            if not file.content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="File must be an image")

            ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
            filename = f"{uuid.uuid4()}.{ext}"
            path = f"uploads/posts/{filename}"

            with open(path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            image_url = f"/uploads/posts/{filename}"

            # ✅ THIS WAS THE MISSING LINE — create PostImage row in DB
            post_image = PostImage(
                id=str(uuid.uuid4()),
                post_id=post.id,
                image_url=image_url,
            )
            db.add(post_image)
            db.commit()

        return {
            "message": "Post created",
            "post_id": post.id,
            "image": image_url,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print("ERROR:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/feed")
def feed(db: Session = Depends(get_db)):
    posts = db.query(Post).order_by(Post.created_at.desc()).all()

    result = []

    for p in posts:
        user = db.query(User).filter(User.id == p.author_id).first()
        images = db.query(PostImage).filter(PostImage.post_id == p.id).all()

        result.append({
            "id": str(p.id),
            "username": user.username if user else "unknown",
            "profile_pic": user.profile_pic if user else None,
            "content": p.content,
            "image": images[0].image_url if images else None,
            "images": [
                {"id": img.id, "image_url": img.image_url}
                for img in images
            ],
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })

    return result


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

# UNCOMMENT THIS:
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

# UNCOMMENT THIS:
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

@app.get("/search")
def search_users(query: str, db: Session = Depends(get_db)):
    users = db.query(User).filter(
        or_(
            User.username.ilike(f"%{query}%"),
            User.full_name.ilike(f"%{query}%")
        )
    ).all()

    return [
        {
            "id": user.id,
            "username": user.username,
            "name": user.full_name,
            "avatar": f"https://sda-app-backend.onrender.com{user.profile_pic}" if user.profile_pic else None
        }
        for user in users
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


# ── CHATS ─────────────────────────────────────────────────

@app.get("/chats")
def get_chats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # IDs of people current user follows
    following = db.query(Follow).filter(
        Follow.follower_id == current_user.id
    ).all()
    following_ids = set(f.following_id for f in following)
 
    # IDs of people who follow current user back
    followers = db.query(Follow).filter(
        Follow.following_id == current_user.id
    ).all()
    follower_ids = set(f.follower_id for f in followers)
 
    # Only mutual: in both sets
    mutual_ids = following_ids & follower_ids
 
    if not mutual_ids:
        return []
 
    users = db.query(User).filter(User.id.in_(mutual_ids)).all()
 
    return [
        {
            "user_id": user.id,
            "username": user.username,
            "profile_pic": f"https://sda-app-backend.onrender.com{user.profile_pic}" if user.profile_pic else None,
            "last_message": "Start chatting 👋",
            "timestamp": None,
        }
        for user in users
    ]
@app.delete("/posts/{post_id}")
def delete_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    db.query(PostImage).filter(PostImage.post_id == post_id).delete()
    db.query(PostLike).filter(PostLike.post_id == post_id).delete()
    db.query(Comment).filter(Comment.post_id == post_id).delete()
    db.delete(post)
    db.commit()
    return {"message": "Post deleted"}


@app.patch("/posts/{post_id}")
async def edit_post(
    post_id: str,
    content: str = Form(...),
    file: UploadFile = File(None),
    remove_image: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    post.content = content

    if remove_image:
        db.query(PostImage).filter(PostImage.post_id == post_id).delete()

    if file and file.filename:
        db.query(PostImage).filter(PostImage.post_id == post_id).delete()
        ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
        filename = f"{uuid.uuid4()}.{ext}"
        path = f"uploads/posts/{filename}"
        with open(path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        db.add(PostImage(
            id=str(uuid.uuid4()),
            post_id=post_id,
            image_url=f"/uploads/posts/{filename}"
        ))

    db.commit()
    return {"message": "Post updated"}


from fastapi import WebSocket, WebSocketDisconnect

# ── GET messages for a conversation ──────────────────────
@app.get("/messages/{conversation_id}")
def get_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # verify user is a participant
    participant = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id,
    ).first()

    if not participant:
        raise HTTPException(status_code=403, detail="Not a participant")

    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()

    return [
        {
            "id": m.id,
            "content": m.content,
            "sender_id": m.sender_id,
            "created_at": m.created_at,
        }
        for m in messages
    ]


# ── POST send a message ───────────────────────────────────
@app.post("/messages/{conversation_id}")
def send_message(
    conversation_id: str,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # verify user is a participant
    participant = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id == current_user.id,
    ).first()

    if not participant:
        raise HTTPException(status_code=403, detail="Not a participant")

    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        sender_id=current_user.id,
        content=content,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    return {
        "id": msg.id,
        "content": msg.content,
        "sender_id": msg.sender_id,
        "created_at": msg.created_at,
    }

@app.get("/conversations/{conversation_id}")
def get_conversation_messages(conversation_id: str, db: Session = Depends(get_db)):
    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()

    return [
        {
            "id": m.id,
            "content": m.content,
            "sender_id": m.sender_id,
            "created_at": m.created_at,
        }
        for m in messages
    ]

@app.post("/conversations")
def create_conversation(
    user_id: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # check if conversation already exists
    existing = db.query(ConversationParticipant).filter(
        ConversationParticipant.user_id.in_([current_user.id, user_id])
    ).all()

    # simple version: always create new
    conversation = Conversation(id=str(uuid.uuid4()))
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    # add both users
    db.add_all([
        ConversationParticipant(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            user_id=current_user.id
        ),
        ConversationParticipant(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            user_id=user_id
        )
    ])
    db.commit()

    return {"conversation_id": conversation.id}


@app.post("/conversations/{other_user_id}")
def create_or_get_conversation(
    other_user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id == other_user_id:
        raise HTTPException(status_code=400, detail="Cannot create conversation with yourself")

    # Step 1: check if conversation already exists between both users
    existing_conversation = (
        db.query(Conversation)
        .join(ConversationParticipant)
        .filter(ConversationParticipant.user_id == current_user.id)
        .all()
    )

    for convo in existing_conversation:
        participants = db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == convo.id
        ).all()

        participant_ids = {p.user_id for p in participants}

        if participant_ids == {current_user.id, other_user_id}:
            return {"conversation_id": convo.id}

    # Step 2: create new conversation
    conversation = Conversation(id=str(uuid.uuid4()))
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    # Step 3: add participants
    db.add_all([
        ConversationParticipant(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            user_id=current_user.id
        ),
        ConversationParticipant(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            user_id=other_user_id
        )
    ])

    db.commit()

    return {"conversation_id": conversation.id}



@app.delete("/messages/{message_id}")
def delete_message(
    message_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 1. Find message
    message = db.query(Message).filter(Message.id == message_id).first()

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # 2. Check ownership (IMPORTANT)
    if str(message.sender_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed to delete this message")

    # 3. Delete message
    db.delete(message)
    db.commit()

    return {"message": "Message deleted successfully"}

@app.put("/messages/{message_id}")
def update_message(message_id: int, body: MessageUpdate, db: Session = Depends(get_db)):
    message = db.query(Message).filter(Message.id == message_id).first()

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    message.content = body.content
    message.edited = True  # optional

    db.commit()
    db.refresh(message)

    return message
 
@app.delete("/messages/{message_id}")
def delete_message(message_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):

    msg = db.query(Message).filter(Message.id == message_id).first()

    if not msg:
        raise HTTPException(status_code=404, detail="Not found")

    if msg.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    db.delete(msg)
    db.commit()

    return {"message": "deleted"}


@app.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Only allow deleting your own account
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not allowed to delete another user's account")
 
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
 
    # Delete all related data first (avoid FK constraint errors)
    db.query(PostLike).filter(PostLike.user_id == user_id).delete()
    db.query(Comment).filter(Comment.author_id == user_id).delete()
 
    # Delete user's post images and posts
    user_posts = db.query(Post).filter(Post.author_id == user_id).all()
    for post in user_posts:
        db.query(PostImage).filter(PostImage.post_id == post.id).delete()
        db.query(PostLike).filter(PostLike.post_id == post.id).delete()
        db.query(Comment).filter(Comment.post_id == post.id).delete()
    db.query(Post).filter(Post.author_id == user_id).delete()
 
    # Delete follow relationships
    db.query(Follow).filter(
        (Follow.follower_id == user_id) | (Follow.following_id == user_id)
    ).delete()
 
    # Delete conversation participations and messages
    participations = db.query(ConversationParticipant).filter(
        ConversationParticipant.user_id == user_id
    ).all()
    for p in participations:
        db.query(Message).filter(Message.conversation_id == p.conversation_id).delete()
        db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == p.conversation_id
        ).delete()
        db.query(Conversation).filter(Conversation.id == p.conversation_id).delete()
 
    # Finally delete the user
    db.delete(user)
    db.commit()
 
    return {"message": "Account deleted successfully"}
@app.post("/forgot-password")
def forgot_password(email: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="No account found with this email")

    token = create_verification_token(email)  # reuse your existing function
    reset_link = f"http://127.0.0.1:8000/reset-password?token={token}"

    # For now just return the link (until you configure email sending)
    return {"message": "Password reset link generated", "reset_link": reset_link}


@app.post("/reset-password")
def reset_password(
    token: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = decode_verification_token(token)  # reuse your existing function
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password = hash_password(new_password)
    db.commit()

    return {"message": "Password reset successful"}

def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.username != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@app.get("/admin/users")
def admin_get_all_users(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    users = db.query(User).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name,
            "email": u.email,
            "profile_pic": u.profile_pic,
        }
        for u in users
    ]


@app.get("/admin/posts")
def admin_get_all_posts(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    posts = db.query(Post).order_by(Post.created_at.desc()).all()
    return [
        {
            "id": p.id,
            "author_id": p.author_id,
            "content": p.content,
            "created_at": p.created_at,
        }
        for p in posts
    ]


@app.delete("/admin/posts/{post_id}")
def admin_delete_post(
    post_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    db.query(PostImage).filter(PostImage.post_id == post_id).delete()
    db.query(PostLike).filter(PostLike.post_id == post_id).delete()
    db.query(Comment).filter(Comment.post_id == post_id).delete()
    db.delete(post)
    db.commit()
    return {"message": f"Post {post_id} deleted by admin"}



@app.delete("/admin/users/{user_id}")
def admin_delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.username == "admin":
        raise HTTPException(status_code=400, detail="Cannot delete admin account")
    db.query(PostLike).filter(PostLike.user_id == user_id).delete()
    db.query(Comment).filter(Comment.author_id == user_id).delete()
    user_posts = db.query(Post).filter(Post.author_id == user_id).all()
    for post in user_posts:
        db.query(PostImage).filter(PostImage.post_id == post.id).delete()
        db.query(PostLike).filter(PostLike.post_id == post.id).delete()
        db.query(Comment).filter(Comment.post_id == post.id).delete()
    db.query(Post).filter(Post.author_id == user_id).delete()
    db.query(Follow).filter(
        (Follow.follower_id == user_id) | (Follow.following_id == user_id)
    ).delete()
    participations = db.query(ConversationParticipant).filter(
        ConversationParticipant.user_id == user_id
    ).all()
    for p in participations:
        db.query(Message).filter(Message.conversation_id == p.conversation_id).delete()
        db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == p.conversation_id
        ).delete()
        db.query(Conversation).filter(Conversation.id == p.conversation_id).delete()
    db.delete(user)
    db.commit()
    return {"message": f"User {user_id} deleted by admin"}

@app.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Only allow deleting your own account
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not allowed to delete another user's account")
 
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
 
    # Delete all related data first (avoid FK constraint errors)
    db.query(PostLike).filter(PostLike.user_id == user_id).delete()
    db.query(Comment).filter(Comment.author_id == user_id).delete()
 
    # Delete user's post images and posts
    user_posts = db.query(Post).filter(Post.author_id == user_id).all()
    for post in user_posts:
        db.query(PostImage).filter(PostImage.post_id == post.id).delete()
        db.query(PostLike).filter(PostLike.post_id == post.id).delete()
        db.query(Comment).filter(Comment.post_id == post.id).delete()
    db.query(Post).filter(Post.author_id == user_id).delete()
 
    # Delete follow relationships
    db.query(Follow).filter(
        (Follow.follower_id == user_id) | (Follow.following_id == user_id)
    ).delete()
 
    # Delete conversation participations and messages
    participations = db.query(ConversationParticipant).filter(
        ConversationParticipant.user_id == user_id
    ).all()
    for p in participations:
        db.query(Message).filter(Message.conversation_id == p.conversation_id).delete()
        db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == p.conversation_id
        ).delete()
        db.query(Conversation).filter(Conversation.id == p.conversation_id).delete()
 
    # Finally delete the user
    db.delete(user)
    db.commit()
 
    return {"message": "Account deleted successfully"}
