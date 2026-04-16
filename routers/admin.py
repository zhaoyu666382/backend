"""
文件位置：backend/routers/admin.py
修复：
  1. 控制台总订单数和链上区块数显示不出来
  2. 系统状态改为动态检测（实际检查各端口是否在线）
  3. 区块链接口正确返回真实数据
"""
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.deps import get_db, require_role
from models import (User, UserRole, Product, Order, OrderItem,
                    OrderStatus, Batch, TraceEvent)
from services.blockchain_service import blockchain

router = APIRouter()


# ══════════════════════════════════════════════════════════
# 数据统计（修复：正确统计订单数和链上区块数）
# ══════════════════════════════════════════════════════════
@router.get("/stats", summary="平台数据统计")
def get_stats(
    db:    Session = Depends(get_db),
    admin  = Depends(require_role("admin")),
) -> Dict[str, Any]:

    user_count    = db.query(User).count()
    product_count = db.query(Product).filter(Product.is_active == True).count()
    order_count   = db.query(Order).count()   # ← 修复：不加任何过滤，统计全部订单

    total_amount = db.query(func.sum(Order.total_amount)).filter(
        Order.status.in_([
            OrderStatus.PAID, OrderStatus.SHIPPED,
            OrderStatus.DELIVERED, OrderStatus.COMPLETED
        ])
    ).scalar() or 0.0

    batch_count = db.query(Batch).count()
    event_count = db.query(TraceEvent).count()

    # 角色分布
    role_dist = {
        "consumer": db.query(User).filter(User.role == UserRole.CONSUMER).count(),
        "farmer":   db.query(User).filter(User.role == UserRole.FARMER).count(),
        "admin":    db.query(User).filter(User.role == UserRole.ADMIN).count(),
    }

    # 订单状态分布
    order_dist = {}
    for status in OrderStatus:
        order_dist[status.value] = db.query(Order).filter(Order.status == status).count()

    # 链状态（真实数据）
    chain = blockchain.stats()

    return {
        "user_count":    user_count,
        "product_count": product_count,
        "order_count":   order_count,      # ← 真实总订单数
        "total_amount":  round(total_amount, 2),
        "batch_count":   batch_count,
        "event_count":   event_count,
        "role_dist":     role_dist,
        "order_dist":    order_dist,
        "chain":         chain,            # ← 真实链数据
    }


# ══════════════════════════════════════════════════════════
# 系统状态（动态检测各端口）
# ══════════════════════════════════════════════════════════
@router.get("/system_status", summary="系统运行状态（动态检测）")
def system_status() -> Dict[str, Any]:
    """
    检测后端和数据库是否正常运行
    前端各端口需要在前端侧检测（fetch自身origin即可）
    """
    import sqlite3
    from config import settings

    # 检测数据库
    db_ok = False
    db_msg = ""
    try:
        conn = sqlite3.connect(str(settings.DATABASE_PATH), timeout=2)
        conn.execute("SELECT 1")
        conn.close()
        db_ok  = True
        db_msg = "连接正常"
    except Exception as e:
        db_msg = str(e)

    # 检测区块链文件
    chain_ok  = settings.BLOCKCHAIN_FILE.exists()
    chain_info= blockchain.stats()

    # 检测AI模型
    pest_model_ok = (settings.BASE_DIR / "ai" / "pest_model.pt").exists()
    rec_model_ok  = (settings.BASE_DIR / "ai" / "rec_model.pt").exists()

    return {
        "backend": {"status": "online", "msg": "后端运行正常"},
        "database": {
            "status": "online" if db_ok else "error",
            "msg":    db_msg,
            "path":   str(settings.DATABASE_PATH),
        },
        "blockchain": {
            "status":       "online" if chain_ok else "warning",
            "block_count":  chain_info["length"],
            "valid":        chain_info["valid"],
            "msg":          "区块链正常" if chain_info["valid"] else "链完整性异常",
        },
        "ai_models": {
            "pest_model": "已加载" if pest_model_ok else "未训练",
            "rec_model":  "已加载" if rec_model_ok  else "未训练",
        },
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ══════════════════════════════════════════════════════════
# 用户管理
# ══════════════════════════════════════════════════════════
@router.get("/users", summary="用户列表")
def list_users(
    db: Session = Depends(get_db),
    admin = Depends(require_role("admin")),
    q: str = Query(default=""),
    page: int = 1, page_size: int = 20,
) -> Dict[str, Any]:
    query = db.query(User)
    if q:
        like = f"%{q}%"
        query = query.filter((User.username.ilike(like)) | (User.email.ilike(like)))
    total = query.count()
    users = query.order_by(User.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [{"id": u.id, "username": u.username, "email": u.email,
                       "role": u.role.value, "is_active": u.is_active,
                       "created_at": u.created_at.isoformat() if u.created_at else None}
                      for u in users]}


@router.post("/users/{user_id}/toggle_active", summary="启用/禁用用户")
def toggle_user(user_id: int, db: Session = Depends(get_db),
                admin = Depends(require_role("admin"))) -> Dict[str, Any]:
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    if u.role == UserRole.ADMIN:
        raise HTTPException(status_code=400, detail="不能禁用管理员账号")
    u.is_active = not u.is_active
    db.commit()
    return {"ok": True, "is_active": u.is_active, "username": u.username}


# ══════════════════════════════════════════════════════════
# 商品管理
# ══════════════════════════════════════════════════════════
@router.get("/products", summary="商品列表（全部）")
def list_products(
    db: Session = Depends(get_db),
    admin = Depends(require_role("admin")),
    q: str = Query(default=""),
    page: int = 1, page_size: int = 20,
) -> Dict[str, Any]:
    query = db.query(Product)
    if q:
        like = f"%{q}%"
        query = query.filter((Product.name.ilike(like)) | (Product.category.ilike(like)))
    total    = query.count()
    products = query.order_by(Product.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [{"id": p.id, "name": p.name, "category": p.category,
                       "price": p.price, "stock": p.stock, "unit": p.unit,
                       "origin": p.origin, "organic_certified": p.organic_certified,
                       "is_active": p.is_active, "farmer_id": p.farmer_id,
                       "created_at": p.created_at.isoformat() if p.created_at else None}
                      for p in products]}


@router.post("/products/{product_id}/toggle_active", summary="上架/下架商品")
def toggle_product(product_id: int, db: Session = Depends(get_db),
                   admin = Depends(require_role("admin"))) -> Dict[str, Any]:
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="商品不存在")
    p.is_active = not p.is_active
    db.commit()
    return {"ok": True, "is_active": p.is_active, "name": p.name}


@router.delete("/products/{product_id}", summary="永久删除商品")
def delete_product(product_id: int, db: Session = Depends(get_db),
                   admin = Depends(require_role("admin"))) -> Dict[str, Any]:
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="商品不存在")
    db.delete(p)
    db.commit()
    return {"ok": True, "msg": f"商品「{p.name}」已永久删除"}


# ══════════════════════════════════════════════════════════
# 订单管理
# ══════════════════════════════════════════════════════════
@router.get("/orders", summary="全部订单")
def list_orders(
    db: Session = Depends(get_db),
    admin = Depends(require_role("admin")),
    q: str = Query(default=""),
    status: str = Query(default=""),
    page: int = 1, page_size: int = 20,
) -> Dict[str, Any]:
    query = db.query(Order)
    if q:
        query = query.filter(Order.order_number.ilike(f"%{q}%"))
    if status:
        try:
            query = query.filter(Order.status == OrderStatus(status))
        except ValueError:
            pass
    total  = query.count()
    orders = query.order_by(Order.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [{"id": o.id, "order_number": o.order_number,
                       "user_id": o.user_id, "total_amount": o.total_amount,
                       "status": o.status.value,
                       "receiver_name": o.receiver_name,
                       "receiver_phone": o.receiver_phone,
                       "shipping_company": o.shipping_company,
                       "tracking_number": o.tracking_number,
                       "created_at": o.created_at.isoformat() if o.created_at else None}
                      for o in orders]}


@router.post("/orders/{order_id}/ship", summary="发货")
def ship_order(order_id: int, payload: dict,
               db: Session = Depends(get_db),
               admin = Depends(require_role("admin"))) -> Dict[str, Any]:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status != OrderStatus.PAID:
        raise HTTPException(status_code=400, detail="仅已支付订单可发货")
    order.status           = OrderStatus.SHIPPED
    order.shipping_company = payload.get("shipping_company", "顺丰速运")
    order.tracking_number  = payload.get("tracking_number", "")
    order.shipped_at       = datetime.now()
    db.commit()
    return {"ok": True, "msg": "发货成功"}


# ══════════════════════════════════════════════════════════
# 区块链接口（真实数据）
# ══════════════════════════════════════════════════════════
@router.get("/chain", summary="区块链状态摘要")
def chain_status(admin = Depends(require_role("admin"))) -> Dict[str, Any]:
    return blockchain.stats()


@router.get("/chain/blocks", summary="区块列表（分页）")
def chain_blocks(
    page: int = 1, page_size: int = 20,
    admin = Depends(require_role("admin")),
) -> Dict[str, Any]:
    return blockchain.get_all_blocks(page=page, page_size=page_size)


@router.get("/chain/verify", summary="验证链完整性")
def chain_verify(admin = Depends(require_role("admin"))) -> Dict[str, Any]:
    valid = blockchain.verify_chain()
    stats = blockchain.stats()
    return {
        "valid":       valid,
        "length":      stats["length"],
        "latest_hash": stats["latest_hash"],
        "message":     "链完整性验证通过，所有数据未被篡改" if valid else "警告：链完整性验证失败！",
    }