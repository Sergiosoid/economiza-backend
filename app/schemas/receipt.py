from pydantic import BaseModel, ConfigDict
from datetime import datetime
from uuid import UUID
from typing import Optional, List, TYPE_CHECKING
from decimal import Decimal

if TYPE_CHECKING:
    from app.schemas.receipt_item import ReceiptItemResponse, ReceiptItemCreate


class ReceiptBase(BaseModel):
    access_key: str
    raw_qr_text: Optional[str] = None
    total_value: Decimal
    subtotal: Decimal
    total_tax: Decimal
    emitted_at: datetime
    store_name: Optional[str] = None
    store_cnpj: Optional[str] = None


class ReceiptCreate(ReceiptBase):
    user_id: UUID
    items: List['ReceiptItemCreate'] = []


class ReceiptResponse(ReceiptBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    items: List['ReceiptItemResponse'] = []

    model_config = ConfigDict(from_attributes=True)


# Forward reference resolution
from app.schemas.receipt_item import ReceiptItemResponse, ReceiptItemCreate
ReceiptCreate.model_rebuild()
ReceiptResponse.model_rebuild()

