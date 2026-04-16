from typing import List

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy.orm import Session

from api.schemas import OrderCreate, OrderOut, OrderShipIn
from core.deps import get_db, get_current_user, require_role
from models import Order, OrderItem, Product, User, OrderStatus

import uuid

router = APIRouter()


def _gen_order_number() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]


@router.post("", response_model=OrderOut, summary="创建订单")
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 1) 计算金额并校验库存
    total = 0.0
    items: List[OrderItem] = []

    for it in payload.items:
        p = db.query(Product).filter(Product.id == it.product_id, Product.is_active == True).first()  # noqa
        if not p:
            raise HTTPException(status_code=404, detail=f"商品不存在：{it.product_id}")
        if p.stock < it.quantity:
            raise HTTPException(status_code=400, detail=f"库存不足：{p.name}")

        unit_price = float(it.unit_price) if it.unit_price else float(p.price)
        subtotal = unit_price * float(it.quantity)
        total += subtotal
        items.append(OrderItem(product_id=p.id, quantity=float(it.quantity), unit_price=unit_price, subtotal=subtotal))

    # 2) 创建订单
    order = Order(
        order_number=_gen_order_number(),
        user_id=user.id,
        total_amount=total,
        status=OrderStatus.PENDING,
        receiver_name=payload.receiver_name or user.username,
        receiver_phone=payload.receiver_phone or (user.phone or "13800000000"),
        receiver_address=payload.receiver_address or (user.address or "默认地址（可在用户资料完善）"),
        remark=payload.remark,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    # 3) 绑定订单项并扣库存（演示版：直接扣；正式版建议事务/锁）
    for oi in items:
        oi.order_id = order.id
        db.add(oi)
        # 扣库存
        p = db.query(Product).filter(Product.id == oi.product_id).first()
        p.stock = int(p.stock - oi.quantity)
    db.commit()
    db.refresh(order)
    return order


@router.get("/mine", response_model=List[OrderOut], summary="我的订单")
def my_orders(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return db.query(Order).filter(Order.user_id == user.id).order_by(Order.created_at.desc()).all()


@router.get("", response_model=List[OrderOut], summary="全部订单（管理员）")
def all_orders(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
    q: str = Query(default="", description="按订单号模糊搜索"),
):
    query = db.query(Order)
    if q:
        query = query.filter(Order.order_number.ilike(f"%{q}%"))
    return query.order_by(Order.created_at.desc()).all()


@router.get("/{order_id}", response_model=OrderOut, summary="订单详情")
def order_detail(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if user.role.value != "admin" and order.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权限查看该订单")
    return order


@router.post("/{order_id}/pay", response_model=OrderOut, summary="模拟支付")
def pay_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if user.role.value != "admin" and order.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权限操作该订单")
    if order.status != OrderStatus.PENDING:
        raise HTTPException(status_code=400, detail="当前状态不可支付")

    order.status = OrderStatus.PAID
    order.payment_method = "模拟支付"
    db.commit()
    db.refresh(order)
    return order


@router.post("/{order_id}/cancel", response_model=OrderOut, summary="取消订单（消费者/管理员）")
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if user.role.value != "admin" and order.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权限操作该订单")
    if order.status not in [OrderStatus.PENDING, OrderStatus.PAID]:
        raise HTTPException(status_code=400, detail="当前状态不可取消")

    order.status = OrderStatus.CANCELLED
    db.commit()
    db.refresh(order)
    return order


@router.post("/{order_id}/ship", response_model=OrderOut, summary="发货（管理员）")
def ship_order(
    order_id: int,
    payload: OrderShipIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status != OrderStatus.PAID:
        raise HTTPException(status_code=400, detail="仅已支付订单可发货")

    order.status = OrderStatus.SHIPPED
    order.shipping_company = payload.shipping_company
    order.tracking_number = payload.tracking_number
    order.shipped_at = datetime.now()
    db.commit()
    db.refresh(order)
    return order


@router.post("/{order_id}/confirm", response_model=OrderOut, summary="确认收货（消费者/管理员）")
def confirm_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if user.role.value != "admin" and order.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权限操作该订单")
    if order.status != OrderStatus.SHIPPED:
        raise HTTPException(status_code=400, detail="仅已发货订单可确认收货")

    order.status = OrderStatus.DELIVERED
    order.delivered_at = datetime.now()
    db.commit()
    db.refresh(order)
    return order
