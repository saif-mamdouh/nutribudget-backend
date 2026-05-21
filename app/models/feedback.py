from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from app.database import Base
import datetime

class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_id    = Column(Integer, nullable=True)
    rating     = Column(Integer, nullable=False)
    notes      = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
