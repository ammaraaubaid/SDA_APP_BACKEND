from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


# ── Users ──────────────────────────────────────────────────
class UserLogin(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: str
    university: Optional[str] = None
    department: Optional[str] = None
    bio: Optional[str] = None  # fixed: was Optional[int], should be str


class UserUpdate(BaseModel):
    # All fields optional — only send what changed
    full_name: Optional[str] = None
    username: Optional[str] = None       # ← added so edit.tsx can update username
    bio: Optional[str] = None
    profile_pic: Optional[str] = None    # ← fixed: was avatar_url, matches User model
    university: Optional[str] = None
    department: Optional[str] = None


class UserOut(BaseModel):
    id: str
    username: str
    full_name: Optional[str] = None
    bio: Optional[str] = None
    profile_pic: Optional[str] = None    # ← fixed: was avatar_url
    university: Optional[str] = None
    department: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Auth ───────────────────────────────────────────────────
class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


# ── Posts ──────────────────────────────────────────────────
class PostCreate(BaseModel):
    content: Optional[str] = None
    visibility: str = "public"
    group_id: Optional[str] = None
    media_urls: Optional[List[str]] = None
    media_type: Optional[str] = "image"


class PostOut(BaseModel):
    id: str
    author_id: str
    content: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Comments ───────────────────────────────────────────────
class CommentCreate(BaseModel):
    content: str
    parent_id: Optional[str] = None


class CommentOut(BaseModel):
    id: str
    post_id: str
    author_id: str
    parent_id: Optional[str] = None
    content: str
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Groups ─────────────────────────────────────────────────
class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_private: bool = False
    university: Optional[str] = None


class GroupOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    is_private: bool
    created_by: str
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Messages ───────────────────────────────────────────────
class ConversationCreate(BaseModel):
    other_user_id: str


class ConversationOut(BaseModel):
    id: str
    created_at: datetime
    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    sender_id: str
    content: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Notifications ──────────────────────────────────────────
class NotificationOut(BaseModel):
    id: str
    type: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    is_read: bool
    created_at: datetime
    model_config = {"from_attributes": True}