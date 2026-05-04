from sqlalchemy import Column, String, DateTime, Text, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.sql import func
from database import Base

# ───────────────── USER ─────────────────
class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)

    full_name = Column(String)
    department = Column(String)
    university = Column(String)
    bio = Column(String)

    profile_pic = Column(String, nullable=True)

    created_at = Column(DateTime, server_default=func.now())


# ───────────────── FOLLOW ─────────────────
class Follow(Base):
    __tablename__ = "follows"

    id = Column(String, primary_key=True)
    follower_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))
    following_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))

    __table_args__ = (
        UniqueConstraint("follower_id", "following_id"),
    )


# ───────────────── POST ─────────────────
class Post(Base):
    __tablename__ = "posts"  

    id = Column(String, primary_key=True)
    author_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))
    content = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


# ───────────────── POST IMAGE ─────────────────
class PostImage(Base):
    
    __tablename__ = "post_images"  

    id = Column(String, primary_key=True)
    post_id = Column(String, ForeignKey("posts.id", ondelete="CASCADE"))
    image_url = Column(String)
    created_at = Column(DateTime, server_default=func.now())


# ───────────────── LIKE ─────────────────
class PostLike(Base):
    __tablename__ = "post_likes"

    id = Column(String, primary_key=True)
    post_id = Column(String, ForeignKey("posts.id", ondelete="CASCADE"))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))


# ───────────────── COMMENT ─────────────────
class Comment(Base):
    __tablename__ = "comments"

    id = Column(String, primary_key=True)
    post_id = Column(String, ForeignKey("posts.id", ondelete="CASCADE"))
    author_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))

    parent_id = Column(String, ForeignKey("comments.id"), nullable=True)

    content = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


# # ───────────────── NOTIFICATION ─────────────────
# class Notification(Base):
#     __tablename__ = "notifications"

#     id = Column(String, primary_key=True)
#     user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))

#     type = Column(String)
#     entity_type = Column(String, nullable=True)
#     entity_id = Column(String, nullable=True)

#     is_read = Column(Boolean, default=False)

#     created_at = Column(DateTime, server_default=func.now())


# # ───────────────── GROUP ─────────────────
# class Group(Base):
#     __tablename__ = "groups"

#     id = Column(String, primary_key=True)
#     name = Column(String)
#     description = Column(Text)

#     is_private = Column(Boolean, default=False)

#     created_by = Column(String, ForeignKey("users.id", ondelete="CASCADE"))
#     university = Column(String, nullable=True)

#     created_at = Column(DateTime, server_default=func.now())


# class GroupMember(Base):
#     __tablename__ = "group_members"

#     id = Column(String, primary_key=True)
#     group_id = Column(String, ForeignKey("groups.id", ondelete="CASCADE"))
#     user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))

#     role = Column(String, default="member")


# ───────────────── CHAT ─────────────────
class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)
    created_at = Column(DateTime, server_default=func.now())


class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"))
    sender_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))

    content = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

