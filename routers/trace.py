"""
文件位置：backend/routers/trace.py
作用：区块链溯源接口
  GET  /api/trace/timeline/{batch_number}  查询批次时间线
  POST /api/trace/event                    录入溯源事件（农户）
  GET  /api/trace/verify/{batch_number}    验证批次链完整性
"""
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.deps import get_db, get_current_user, require_role
from models import Batch, TraceEvent, Product, User
from services.blockchain_service import blockchain

router = APIRouter()


# ── Pydantic 请求体 ──────────────────────────────────────────
class TraceEventCreate(BaseModel):
    batch_id:    int
    event_type:  str
    location:    Optional[str] = None
    description: Optional[str] = None
    event_time:  Optional[str] = None   # ISO 格式，可选，默认当前时间


# ── 录入溯源事件 ─────────────────────────────────────────────
@router.post("/event", summary="录入溯源事件（农户）")
def add_trace_event(
    payload: TraceEventCreate,
    db:   Session = Depends(get_db),
    user: User    = Depends(require_role("farmer", "admin")),
) -> Dict[str, Any]:

    # 查找批次
    batch = db.query(Batch).filter(Batch.id == payload.batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")

    # 解析事件时间
    if payload.event_time:
        try:
            evt_time = datetime.fromisoformat(payload.event_time)
        except ValueError:
            evt_time = datetime.now()
    else:
        evt_time = datetime.now()

    # 写入区块链（本地 JSON 链）
    block_hash = blockchain.anchor(
        batch_number=batch.batch_number,
        event_type=payload.event_type,
        location=payload.location or "",
        description=payload.description or "",
        operator=user.username,
    )

    # 写入数据库
    event = TraceEvent(
        batch_id=payload.batch_id,
        event_type=payload.event_type,
        location=payload.location,
        description=payload.description,
        event_time=evt_time,
        blockchain_hash=block_hash,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    return {
        "ok":             True,
        "event_id":       event.id,
        "blockchain_hash": block_hash,
        "msg":            f"溯源事件已录入并上链，区块哈希：{block_hash[:16]}...",
    }


# ── 查询批次时间线 ───────────────────────────────────────────
@router.get("/timeline/{batch_number}", summary="查询批次溯源时间线")
def get_timeline(
    batch_number: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:

    batch = db.query(Batch).filter(Batch.batch_number == batch_number).first()
    if not batch:
        raise HTTPException(status_code=404, detail=f"批次 {batch_number} 不存在")

    product = db.query(Product).filter(Product.id == batch.product_id).first()

    events = (
        db.query(TraceEvent)
        .filter(TraceEvent.batch_id == batch.id)
        .order_by(TraceEvent.event_time.asc())
        .all()
    )

    # 从区块链获取对应区块（用于验证）
    chain_blocks = blockchain.get_blocks_by_batch(batch_number)
    chain_valid  = blockchain.verify_chain()

    return {
        "batch": {
            "id":              batch.id,
            "batch_number":    batch.batch_number,
            "production_date": batch.production_date.isoformat() if batch.production_date else None,
            "expiry_date":     batch.expiry_date.isoformat()     if batch.expiry_date     else None,
            "quantity":        batch.quantity,
        },
        "product": {
            "id":     product.id     if product else None,
            "name":   product.name   if product else "未知商品",
            "origin": product.origin if product else None,
        },
        "events": [
            {
                "id":               e.id,
                "event_type":       e.event_type,
                "location":         e.location,
                "description":      e.description,
                "event_time":       e.event_time.isoformat() if e.event_time else None,
                "blockchain_hash":  e.blockchain_hash,
            }
            for e in events
        ],
        "chain_valid":   chain_valid,
        "chain_blocks":  len(chain_blocks),
        "total_blocks":  blockchain.stats()["length"],
    }


# ── 验证链完整性 ─────────────────────────────────────────────
@router.get("/verify/{batch_number}", summary="验证批次区块链完整性")
def verify_batch(
    batch_number: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:

    chain_valid   = blockchain.verify_chain()
    chain_blocks  = blockchain.get_blocks_by_batch(batch_number)
    stats         = blockchain.stats()

    return {
        "batch_number": batch_number,
        "chain_valid":  chain_valid,
        "chain_length": stats["length"],
        "batch_blocks": len(chain_blocks),
        "latest_hash":  stats["latest_hash"],
        "message":      "链完整性验证通过，数据未被篡改" if chain_valid else "警告：链完整性验证失败！",
    }