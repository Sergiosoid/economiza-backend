from sqlalchemy import Column, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class ShoppingListExecution(Base):
    __tablename__ = "shopping_list_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    shopping_list_id = Column(UUID(as_uuid=True), ForeignKey("shopping_lists.id", ondelete="CASCADE"), nullable=False, index=True)
    receipt_id = Column(UUID(as_uuid=True), ForeignKey("receipts.id", ondelete="SET NULL"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    planned_total = Column(Numeric(12, 2), nullable=True)
    real_total = Column(Numeric(12, 2), nullable=True)
    difference = Column(Numeric(12, 2), nullable=True)
    difference_percent = Column(Numeric(6, 2), nullable=True)
    summary = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    shopping_list = relationship("ShoppingList", backref="executions")
    receipt = relationship("Receipt", backref="shopping_list_executions")
    user = relationship("User", backref="shopping_list_executions")

