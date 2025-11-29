from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base


class CreditUsage(Base):
    __tablename__ = "credit_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    credits_consumed = Column(Integer, nullable=False)
    action_type = Column(String(50), nullable=False, index=True)  # 'scan', 'ai_analysis', etc.
    action_id = Column(UUID(as_uuid=True), nullable=True)  # ID do receipt, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

