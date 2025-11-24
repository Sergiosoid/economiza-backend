from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


class ExampleBase(BaseModel):
    name: str
    description: Optional[str] = None


class ExampleCreate(ExampleBase):
    pass


class ExampleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ExampleResponse(ExampleBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

