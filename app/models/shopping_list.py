from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Numeric, Integer
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class ShoppingList(Base):
    __tablename__ = "shopping_lists"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False, default="Minha lista")
    is_shared = Column(Boolean, default=False, nullable=False)
    meta = Column(JSON, nullable=True)  # para flags futuras: { "mode": "family", ... }
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    items = relationship("ShoppingListItem", back_populates="shopping_list", cascade="all, delete-orphan")
    user = relationship("User", backref="shopping_lists")


class ShoppingListItem(Base):
    __tablename__ = "shopping_list_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    shopping_list_id = Column(UUID(as_uuid=True), ForeignKey("shopping_lists.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    description = Column(String(255), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False)  # sempre armazenar na menor unidade (ex: g, mL ou un)
    unit_code = Column(String(10), nullable=False)  # ex: "g", "kg", "ml", "L", "un"
    unit_type = Column(String(16), nullable=False)  # weight/volume/unit/custom
    unit_multiplier = Column(Integer, nullable=False)  # para conversões (copiado da Unit no momento de criação)
    price_estimate = Column(Numeric(12, 2), nullable=True)  # preço unitário estimado (por unidade base)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    shopping_list = relationship("ShoppingList", back_populates="items")
    product = relationship("Product", backref="shopping_list_items")

