"""
文件位置：backend/routers/batches.py
作用：批次管理接口
  POST /api/batches          创建批次（农户）
  GET  /api/batches          查询批次列表
  GET  /api/batches/{id}     批次详情
"""
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.deps import get_db, get_current_user, require_role
from models import Batch, Product, TraceEvent, User
from services.blockchain_service import blockchain

router = APIRouter()


class BatchCreate(BaseModel):
    product_id:       int
    batch_number:     Optional[str] = None    # 不填则自动生成
    quantity:         float
    production_date:  Optional[str] = None    # YYYY-MM-DD
    expiry_date:      Optional[str] = None    # YYYY-MM-DD


@router.post("", summary="创建批次（农户）")
def create_batch(
    payload: BatchCreate,
    db:   Session = Depends(get_db),
    user: User    = Depends(require_role("farmer", "admin")),
) -> Dict[str, Any]:

    product = db.query(Product).filter(Product.id == payload.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    # 自动生成批次编号
    batch_number = payload.batch_number or (
        f"BN{datetime.now().strftime('%Y%m%d%H%M%S')}{payload.product_id:03d}"
    )

    # 检查批次号是否重复
    if db.query(Batch).filter(Batch.batch_number == batch_number).first():
        raise HTTPException(status_code=400, detail=f"批次编号 {batch_number} 已存在")

    prod_date = (
        datetime.strptime(payload.production_date, "%Y-%m-%d")
        if payload.production_date else datetime.now()
    )
    exp_date = (
        datetime.strptime(payload.expiry_date, "%Y-%m-%d")
        if payload.expiry_date else prod_date + timedelta(days=180)
    )

    batch = Batch(
        product_id=payload.product_id,
        batch_number=batch_number,
        quantity=payload.quantity,
        production_date=prod_date,
        expiry_date=exp_date,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    # 创建批次时自动写入区块链（创世事件）
    block_hash = blockchain.anchor(
        batch_number=batch_number,
        event_type="批次创建",
        location=product.origin or "农场",
        description=f"商品：{product.name}，数量：{payload.quantity}{product.unit}，批次创建上链存证",
        operator=user.username,
    )

    # 同时写入一条溯源事件
    db.add(TraceEvent(
        batch_id=batch.id,
        event_type="批次创建",
        location=product.origin or "农场",
        description=f"批次 {batch_number} 创建，商品：{product.name}",
        event_time=datetime.now(),
        blockchain_hash=block_hash,
    ))
    db.commit()

    return {
        "ok":             True,
        "batch_id":       batch.id,
        "batch_number":   batch_number,
        "blockchain_hash": block_hash,
        "msg":            f"批次创建成功并已上链！批次编号：{batch_number}",
    }


@router.get("", summary="批次列表（农户查自己的，管理员查全部）")
def list_batches(
    db:   Session = Depends(get_db),
    user: User    = Depends(get_current_user),
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:

    query = db.query(Batch)

    # 农户只能看自己商品的批次
    if user.role.value == "farmer":
        my_product_ids = [
            r[0] for r in db.query(Product.id).filter(Product.farmer_id == user.id).all()
        ]
        query = query.filter(Batch.product_id.in_(my_product_ids))

    total   = query.count()
    batches = query.order_by(Batch.production_date.desc()) \
                   .offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for b in batches:
        product = db.query(Product).filter(Product.id == b.product_id).first()
        event_count = db.query(TraceEvent).filter(TraceEvent.batch_id == b.id).count()
        items.append({
            "id":              b.id,
            "batch_number":    b.batch_number,
            "product_name":    product.name if product else "未知",
            "quantity":        b.quantity,
            "unit":            product.unit if product else "",
            "production_date": b.production_date.strftime("%Y-%m-%d") if b.production_date else None,
            "expiry_date":     b.expiry_date.strftime("%Y-%m-%d")     if b.expiry_date     else None,
            "event_count":     event_count,
            "on_chain":        event_count > 0,
        })

    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/{batch_id}", summary="批次详情")
def get_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    user: User  = Depends(get_current_user),
) -> Dict[str, Any]:

    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")

    product = db.query(Product).filter(Product.id == batch.product_id).first()
    events  = db.query(TraceEvent).filter(TraceEvent.batch_id == batch_id) \
                .order_by(TraceEvent.event_time.asc()).all()

    return {
        "batch": {
            "id":            batch.id,
            "batch_number":  batch.batch_number,
            "quantity":      batch.quantity,
            "production_date": batch.production_date.isoformat() if batch.production_date else None,
            "expiry_date":     batch.expiry_date.isoformat()     if batch.expiry_date     else None,
        },
        "product": {
            "id":     product.id     if product else None,
            "name":   product.name   if product else "未知",
            "origin": product.origin if product else None,
        },
        "events": [
            {
                "id":              e.id,
                "event_type":      e.event_type,
                "location":        e.location,
                "description":     e.description,
                "event_time":      e.event_time.isoformat() if e.event_time else None,
                "blockchain_hash": e.blockchain_hash,
            }
            for e in events
        ],
    }