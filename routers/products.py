"""
文件位置：backend/routers/products.py
新增：
  POST /api/products/upload_image  图片上传接口（农户发布新产品用）
  DELETE /api/products/{id}        永久删除商品（解决删除后还能看到的问题）
"""
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from core.deps import get_db, get_current_user, require_role
from models import Product, ProductView, User, UserRole

router = APIRouter()


# ── 请求体 ──────────────────────────────────────────────────────
class ProductCreate(BaseModel):
    name:              str
    description:       Optional[str] = None
    category:          str
    price:             float
    stock:             int
    unit:              str = "kg"
    origin:            Optional[str] = None
    organic_certified: bool = False
    image_url:         Optional[str] = None


class ProductUpdate(BaseModel):
    name:              Optional[str]   = None
    description:       Optional[str]  = None
    price:             Optional[float] = None
    stock:             Optional[int]   = None
    origin:            Optional[str]  = None
    organic_certified: Optional[bool] = None
    image_url:         Optional[str]  = None


# ── 图片上传 ─────────────────────────────────────────────────────
@router.post("/upload_image", summary="上传产品图片（农户）")
async def upload_product_image(
    file: UploadFile = File(...),
    user: User       = Depends(require_role("farmer", "admin")),
) -> Dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="请选择图片文件")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        raise HTTPException(status_code=400, detail="只支持 JPG/PNG/WebP 格式图片")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片大小不能超过 5MB")

    # 保存到 uploads/products/
    upload_dir = Path(settings.UPLOAD_DIR) / "products"
    upload_dir.mkdir(parents=True, exist_ok=True)
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"{ts}_user{user.id}{suffix}"
    save_path = upload_dir / filename
    save_path.write_bytes(content)

    url = f"http://localhost:8000/static/products/{filename}"
    return {"ok": True, "url": url, "filename": filename}


# ── 商品列表 ─────────────────────────────────────────────────────
@router.get("", summary="商品列表")
def list_products(
    db:        Session = Depends(get_db),
    q:         str     = Query(default=""),
    category:  str     = Query(default=""),
    page:      int     = 1,
    page_size: int     = 12,
) -> Dict[str, Any]:
    query = db.query(Product).filter(Product.is_active == True)
    if q:
        like  = f"%{q}%"
        query = query.filter(
            (Product.name.ilike(like)) | (Product.category.ilike(like))
        )
    if category:
        query = query.filter(Product.category == category)

    total    = query.count()
    products = query.order_by(Product.created_at.desc()) \
                    .offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [_to_dict(p) for p in products],
        "page":  {"total": total, "page": page, "page_size": page_size},
    }


@router.get("/categories", summary="商品分类列表")
def list_categories(db: Session = Depends(get_db)) -> Dict[str, Any]:
    rows = db.query(Product.category).filter(
        Product.is_active == True, Product.category != None
    ).distinct().all()
    return {"items": [r[0] for r in rows if r[0]]}


@router.get("/{product_id}", summary="商品详情")
def get_product(product_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="商品不存在")
    return _to_dict(p)


@router.post("/{product_id}/view", summary="记录浏览")
def record_view(
    product_id: int,
    db:   Session = Depends(get_db),
    user: User    = Depends(get_current_user),
) -> Dict[str, Any]:
    p = db.query(Product).filter(Product.id == product_id, Product.is_active == True).first()
    if not p:
        return {"ok": False}
    db.add(ProductView(user_id=user.id, product_id=product_id))
    db.commit()
    return {"ok": True}


# ── 创建商品（农户）────────────────────────────────────────────
@router.post("", summary="发布商品（农户）")
def create_product(
    payload: ProductCreate,
    db:      Session = Depends(get_db),
    user:    User    = Depends(require_role("farmer", "admin")),
) -> Dict[str, Any]:
    p = Product(
        name=payload.name,
        description=payload.description,
        category=payload.category,
        price=payload.price,
        stock=payload.stock,
        unit=payload.unit,
        origin=payload.origin,
        organic_certified=payload.organic_certified,
        image_url=payload.image_url,
        farmer_id=user.id,
        is_active=False,   # 农户发布的商品默认下架，管理员审核后上架
    )
    db.add(p); db.commit(); db.refresh(p)
    return {"ok": True, "id": p.id, "msg": "产品发布成功，等待管理员审核上架"}


# ── 更新商品 ────────────────────────────────────────────────────
@router.put("/{product_id}", summary="更新商品（农户/管理员）")
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db:      Session = Depends(get_db),
    user:    User    = Depends(require_role("farmer", "admin")),
) -> Dict[str, Any]:
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="商品不存在")
    if user.role == UserRole.FARMER and p.farmer_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作他人商品")

    for field, val in payload.dict(exclude_none=True).items():
        setattr(p, field, val)
    db.commit()
    return {"ok": True, "msg": "更新成功"}


# ── 永久删除商品（解决删除后还能看到的问题）───────────────────────
@router.delete("/{product_id}", summary="永久删除商品")
def delete_product(
    product_id: int,
    db:   Session = Depends(get_db),
    user: User    = Depends(require_role("farmer", "admin")),
) -> Dict[str, Any]:
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="商品不存在")
    if user.role == UserRole.FARMER and p.farmer_id != user.id:
        raise HTTPException(status_code=403, detail="无权删除他人商品")
    name = p.name
    db.delete(p)
    db.commit()
    return {"ok": True, "msg": f"商品「{name}」已永久删除"}


def _to_dict(p: Product) -> Dict:
    return {
        "id": p.id, "name": p.name, "description": p.description,
        "category": p.category, "price": p.price, "stock": p.stock,
        "unit": p.unit, "origin": p.origin,
        "organic_certified": p.organic_certified,
        "image_url": p.image_url, "farmer_id": p.farmer_id,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }