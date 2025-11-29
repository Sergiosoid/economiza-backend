"""
Schemas Pydantic para notificações
"""
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class NotificationResponse(BaseModel):
    id: UUID
    user_id: UUID
    type: str
    payload: Optional[dict] = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class MarkReadRequest(BaseModel):
    notification_ids: List[UUID]


class MarkReadResponse(BaseModel):
    success: bool
    marked_count: int

