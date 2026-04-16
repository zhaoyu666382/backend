from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


# -------- Auth / User --------
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(default="consumer", description="consumer | farmer | admin")


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: str
    phone: Optional[str] = None
    address: Optional[str] = None
    is_active: bool
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# -------- Product --------
class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    category: Optional[str] = None
    price: float = Field(gt=0)
    stock: int = Field(ge=0)
    unit: str = Field(default="kg")
    image_url: Optional[str] = None
    origin: Optional[str] = None
    organic_certified: bool = False


class ProductOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    price: float
    stock: int
    unit: str
    image_url: Optional[str] = None
    origin: Optional[str] = None
    organic_certified: bool = False
    farmer_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PageOut(BaseModel):
    total: int
    page: int
    page_size: int


class ProductPageOut(BaseModel):
    page: PageOut
    items: List[ProductOut]


# -------- Order --------
class OrderItemCreate(BaseModel):
    product_id: int
    quantity: float = Field(gt=0)
    unit_price: Optional[float] = None  # 允许前端不传，由后端以当前商品价格为准


class OrderCreate(BaseModel):
    items: List[OrderItemCreate] = Field(min_length=1)
    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    receiver_address: Optional[str] = None
    remark: Optional[str] = None


class OrderItemOut(BaseModel):
    id: int
    product_id: int
    quantity: float
    unit_price: float
    subtotal: float

    class Config:
        from_attributes = True


class OrderOut(BaseModel):
    id: int
    order_number: str
    user_id: int
    total_amount: float
    status: str
    payment_method: Optional[str] = None

    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    receiver_address: Optional[str] = None

    shipping_company: Optional[str] = None
    tracking_number: Optional[str] = None
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None

    remark: Optional[str] = None
    created_at: datetime

    order_items: List[OrderItemOut] = []

    class Config:
        from_attributes = True


class OrderShipIn(BaseModel):
    shipping_company: str = Field(min_length=1, max_length=100)
    tracking_number: str = Field(min_length=1, max_length=100)


# -------- Batch / Trace --------
class BatchCreate(BaseModel):
    product_id: int
    batch_number: str = Field(min_length=3, max_length=100)
    quantity: float
    production_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None


class BatchOut(BaseModel):
    id: int
    product_id: int
    batch_number: str
    quantity: float
    production_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    blockchain_hash: Optional[str] = None
    blockchain_timestamp: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TraceEventCreate(BaseModel):
    batch_id: int
    event_type: str = Field(min_length=1, max_length=50)
    description: Optional[str] = None
    location: Optional[str] = None
    event_time: Optional[datetime] = None
    documents: Optional[str] = None


class TraceEventOut(BaseModel):
    id: int
    batch_id: int
    event_type: str
    description: Optional[str] = None
    location: Optional[str] = None
    event_time: datetime
    documents: Optional[str] = None
    blockchain_hash: Optional[str] = None
    blockchain_timestamp: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TimelineOut(BaseModel):
    batch: BatchOut
    product: ProductOut
    events: List[TraceEventOut]
    chain_valid: bool
