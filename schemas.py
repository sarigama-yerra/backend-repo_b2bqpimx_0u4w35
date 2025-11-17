"""
Inventory Management Schemas (Arabic-first)

Each Pydantic model corresponds to a MongoDB collection (lowercased name).
- User -> "user"
- Store -> "store"
- Product -> "product"
- Sale -> "sale"
- InventoryAlert -> "inventoryalert"

Notes:
- Stock is tracked per store inside Product.stocks
- Sales deduct from a single store's stock
- Transfers move quantity from one store to another
"""

from __future__ import annotations
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict
from datetime import datetime


class User(BaseModel):
    name: str = Field(..., description="الاسم الكامل")
    email: EmailStr = Field(..., description="البريد الإلكتروني")
    role: str = Field("manager", description="الدور: admin/manager/seller")
    phone: Optional[str] = Field(None, description="رقم الجوال")
    is_active: bool = Field(True, description="حالة المستخدم")


class Store(BaseModel):
    id: str = Field(..., description="معرّف الفرع")
    name: str = Field(..., description="اسم الفرع")
    city: Optional[str] = Field(None, description="المدينة")
    phone: Optional[str] = Field(None, description="هاتف الفرع")
    address: Optional[str] = Field(None, description="العنوان")


class ProductStock(BaseModel):
    store_id: str = Field(..., description="معرّف الفرع")
    qty: int = Field(0, ge=0, description="الكمية المتوفرة")


class Product(BaseModel):
    sku: str = Field(..., description="رمز المنتج/الباركود")
    name: str = Field(..., description="اسم المنتج")
    category: str = Field("إكسسوارات", description="الفئة")
    price: float = Field(..., ge=0, description="السعر")
    currency: str = Field("SAR", description="العملة")
    low_threshold: int = Field(5, ge=0, description="حد الانخفاض")
    stocks: List[ProductStock] = Field(default_factory=list, description="الأرصدة لكل فرع")
    unit: str = Field("قطعة", description="وحدة القياس")


class SaleItem(BaseModel):
    sku: str
    name: str
    qty: int = Field(..., ge=1)
    price: float = Field(..., ge=0)


class Sale(BaseModel):
    store_id: str
    items: List[SaleItem]
    total: float = Field(..., ge=0)
    currency: str = Field("SAR")
    cashier: Optional[str] = Field(None, description="اسم البائع")
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow)


class InventoryAlert(BaseModel):
    sku: str
    name: str
    level: str = Field(..., description="low أو out")
    total_qty: int = Field(..., ge=0)


class TransferRequest(BaseModel):
    sku: str
    from_store_id: str
    to_store_id: str
    qty: int = Field(..., ge=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    token: str
    user: Dict[str, str]


# Response wrappers
class CreateResponse(BaseModel):
    id: str
    status: str = "ok"


class MessageResponse(BaseModel):
    status: str = "ok"
    message: str = "تم"
