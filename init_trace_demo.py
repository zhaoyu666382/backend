"""
文件位置：backend/init_trace_demo.py
运行方式：cd backend && python init_trace_demo.py
作用：一键为所有在售商品创建批次和5条溯源事件（演示数据）
"""
import sys
sys.path.insert(0, '.')

from database import SessionLocal
from models import Product, Batch, TraceEvent
from services.blockchain_service import blockchain
from datetime import datetime, timedelta

db = SessionLocal()

EVENTS = [
    ("播种/育苗",  "按绿色标准播种，记录温湿度，确保生长环境达标",  "农场A区"),
    ("田间管理",   "施用有机肥，人工除草，记录生长状态和病虫监测",  "农场A区"),
    ("质量检测",   "第三方机构抽样检测，农残检测通过，品质合格",    "质量检测中心"),
    ("采收/分拣",  "人工采收，按等级分拣包装，附质量合格证",        "农场B区"),
    ("出库运输",   "冷链车运输，全程温度监控，已到达消费者仓储中心", "物流配送中心"),
]

products = db.query(Product).filter(Product.is_active == True).all()
print(f"发现 {len(products)} 个在售商品，开始初始化溯源数据...\n")

created = 0
skipped = 0

for p in products:
    if db.query(Batch).filter(Batch.product_id == p.id).first():
        print(f"  [跳过] {p.name}（已有批次）")
        skipped += 1
        continue

    bn = f"BN{datetime.now().strftime('%Y%m%d')}{p.id:03d}"
    batch = Batch(
        product_id=p.id,
        batch_number=bn,
        quantity=float(p.stock),
        production_date=datetime.now() - timedelta(days=10),
        expiry_date=datetime.now() + timedelta(days=180),
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    for i, (etype, desc, loc) in enumerate(EVENTS):
        evt_time = datetime.now() - timedelta(days=9 - i * 2)
        hash_    = blockchain.anchor(bn, etype, loc, desc, "system")
        db.add(TraceEvent(
            batch_id=batch.id,
            event_type=etype,
            location=loc,
            description=desc,
            event_time=evt_time,
            blockchain_hash=hash_,
        ))
    db.commit()
    print(f"  [完成] {p.name} -> 批次 {bn}，5条溯源事件已上链")
    created += 1

db.close()
print(f"\n初始化完成！新建 {created} 个批次，跳过 {skipped} 个。")
print("\n可以在消费者端使用以下批次号查询溯源（根据商品ID对应）：")
print("  格式：BN + 今天日期(8位) + 商品ID(3位，如001, 002...)")
print("  例如：BN20240601001")