from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base


class Unit(Base):
    __tablename__ = "units"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(10), nullable=False, unique=True, index=True)
    name = Column(String(64), nullable=False)
    type = Column(String(16), nullable=False)  # "weight" | "volume" | "unit" | "custom"
    multiplier = Column(Integer, nullable=False)  # valor em menor unidade
    created_at = Column(DateTime(timezone=True), server_default=func.now())

