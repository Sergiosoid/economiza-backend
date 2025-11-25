from pydantic import BaseModel, ConfigDict
from datetime import datetime
from uuid import UUID
from typing import Optional
from app.schemas.category import CategoryResponse


class ProductBase(BaseModel):
    normalized_name: str
    barcode: Optional[str] = None
    category_id: Optional[UUID] = None


class ProductResponse(ProductBase):
    id: UUID
    created_at: datetime
    category: Optional[CategoryResponse] = None

    model_config = ConfigDict(from_attributes=True)

