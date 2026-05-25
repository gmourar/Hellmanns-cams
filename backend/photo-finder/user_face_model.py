from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Index, UniqueConstraint
from sqlalchemy.sql import func
from app.config.admin_db import AdminBase


class UserFace(AdminBase):
    __tablename__ = "user_faces"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    event_id = Column(String(50), nullable=False, index=True)
    rekognition_face_id = Column(String(255), nullable=True)
    collection_id = Column(String(255), nullable=False)
    registered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uq_user_face_user_event"),
        Index("idx_user_faces_user_id", "user_id"),
        Index("idx_user_faces_event_id", "event_id"),
    )
