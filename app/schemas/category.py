from pydantic import BaseModel, ConfigDict
from datetime import datetime
from uuid import UUID


class CategoryBase(BaseModel):
    name: str


class CategoryResponse(CategoryBase):
    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

