from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    access_key = Column(String(255), nullable=False, index=True)
    raw_qr_text = Column(String(500), nullable=True)
    total_value = Column(Numeric(10, 2), nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)
    total_tax = Column(Numeric(10, 2), nullable=False)
    emitted_at = Column(DateTime(timezone=True), nullable=False)
    store_name = Column(String(255), nullable=True)
    store_cnpj = Column(String(18), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="receipts")
    items = relationship("ReceiptItem", back_populates="receipt", cascade="all, delete-orphan")

