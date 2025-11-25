from pydantic import BaseModel, ConfigDict
from datetime import datetime
from uuid import UUID
from typing import Optional
from decimal import Decimal


class ReceiptItemBase(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal
    total_price: Decimal
    tax_value: Decimal


class ReceiptItemCreate(ReceiptItemBase):
    receipt_id: Optional[UUID] = None
    product_id: Optional[UUID] = None


class ReceiptItemResponse(ReceiptItemBase):
    id: UUID
    receipt_id: UUID
    product_id: Optional[UUID] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

