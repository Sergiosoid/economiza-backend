"""
Schemas Pydantic para listas de compras
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from uuid import UUID
from datetime import datetime


class UnitResponse(BaseModel):
    id: UUID
    code: str
    name: str
    type: str
    multiplier: int

    class Config:
        from_attributes = True


class ShoppingListItemCreate(BaseModel):
    description: str = Field(..., max_length=255)
    quantity: float = Field(..., gt=0, description="Quantidade na menor unidade (ex: gramas, mililitros)")
    unit_code: str = Field(..., max_length=10, description="Código da unidade (ex: 'g', 'kg', 'ml', 'L', 'un')")
    product_id: Optional[UUID] = None


class ShoppingListItemResponse(BaseModel):
    id: UUID
    shopping_list_id: UUID
    product_id: Optional[UUID] = None
    description: str
    quantity: float
    unit_code: str
    unit_type: str
    unit_multiplier: int
    price_estimate: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ShoppingListCreate(BaseModel):
    name: str = Field(default="Minha lista", max_length=200)
    items: List[ShoppingListItemCreate] = Field(default_factory=list)


class ShoppingListResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    is_shared: bool
    meta: Optional[dict] = None
    items: List[ShoppingListItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ShoppingListItemEstimateResponse(BaseModel):
    id: UUID
    description: str
    quantity: float
    unit_code: str
    unit_price_estimate: Optional[float] = None
    total_price_estimate: Optional[float] = None
    confidence: float


class ShoppingListEstimateResponse(BaseModel):
    list_id: UUID
    total_estimate: Optional[float] = None
    items: List[ShoppingListItemEstimateResponse] = Field(default_factory=list)


class ItemComparisonResponse(BaseModel):
    id: Optional[str] = None  # shopping_list_item.id se aplicável, ou null
    description: str
    planned_quantity: Optional[float] = None
    planned_unit_code: Optional[str] = None
    real_quantity: Optional[float] = None
    real_unit_code: Optional[str] = None
    planned_unit_price: Optional[float] = None
    real_unit_price: Optional[float] = None
    planned_total: Optional[float] = None
    real_total: Optional[float] = None
    difference: Optional[float] = None  # real_total - planned_total
    difference_percent: Optional[float] = None
    status: Literal[
        'PLANNED_AND_MATCHED',
        'PLANNED_NOT_PURCHASED',
        'PURCHASED_NOT_PLANNED',
        'PRICE_HIGHER_THAN_EXPECTED',
        'PRICE_LOWER_THAN_EXPECTED',
        'QUANTITY_DIFFERENT'
    ]


class ShoppingListSyncResponse(BaseModel):
    list_id: UUID
    receipt_id: UUID
    summary: dict  # planned_total, real_total, difference, difference_percent, items_planned, items_purchased, items_missing, items_extra
    items: List[ItemComparisonResponse] = Field(default_factory=list)
    execution_id: UUID
    created_at: datetime

