"""
文件位置：backend/routers/agritourism.py
修复：农旅融合图片路径问题

图片放置位置：backend/uploads/agritourism/
访问URL格式：http://localhost:8000/static/agritourism/文件名.jpg

需要准备的图片文件（放到 backend/uploads/agritourism/ 目录）：
农场风景5张：scene_rice.jpg / scene_fruit.jpg / scene_farm.jpg / scene_bee.jpg / scene_veggie.jpg
认养计划6张：adopt_rice.jpg / adopt_apple.jpg / adopt_chicken.jpg / adopt_veggie.jpg / adopt_bee.jpg / adopt_pig.jpg
体验活动6张：act_strawberry.jpg / act_farming.jpg / act_cooking.jpg / act_bee.jpg / act_family.jpg / act_harvest.jpg
"""
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.deps import get_db, get_current_user, require_role
from models import User, AdoptionOrder, ActivityBooking, AdoptionStatus

router = APIRouter()

# 图片基础URL（和 backend/app.py 中的 StaticFiles 挂载一致）
# app.mount("/static", StaticFiles(directory="uploads"), name="static")
# 所以 uploads/agritourism/xxx.jpg → http://localhost:8000/static/agritourism/xxx.jpg
_IMG = "http://localhost:8000/static/agritourism"

FARM_SCENES = [
    {"id": 1, "title": "有机稻田", "emoji": "🌾",
     "image_url": f"{_IMG}/scene_rice.jpg",
     "desc": "连片稻田随风起伏，采用传统人工插秧，全程不施化肥农药，守护一方净土。",
     "tags": ["有机认证", "无农药", "人工种植"], "location": "农场A区·稻田片区"},
    {"id": 2, "title": "果树园", "emoji": "🍎",
     "image_url": f"{_IMG}/scene_fruit.jpg",
     "desc": "苹果、梨、桃等多品种果树百余棵，四季有果可摘，春赏花秋采果，自然生态。",
     "tags": ["可采摘", "多品种", "四季皆宜"], "location": "农场B区·果园片区"},
    {"id": 3, "title": "散养牧场", "emoji": "🐄",
     "image_url": f"{_IMG}/scene_farm.jpg",
     "desc": "黑猪、土鸡、羊在草地上自由奔跑，纯粮饲养，无激素，可近距离接触。",
     "tags": ["散养", "纯粮饲料", "可互动"], "location": "农场C区·牧场片区"},
    {"id": 4, "title": "蜜蜂养殖基地", "emoji": "🐝",
     "image_url": f"{_IMG}/scene_bee.jpg",
     "desc": "百箱蜜蜂采百花之蜜，可参观蜂巢、了解采蜜过程，现场品尝原蜜，老少皆宜。",
     "tags": ["科普体验", "原蜜品尝", "亲子友好"], "location": "农场D区·蜂场片区"},
    {"id": 5, "title": "蔬菜大棚", "emoji": "🥬",
     "image_url": f"{_IMG}/scene_veggie.jpg",
     "desc": "四季蔬菜大棚，番茄、黄瓜、生菜等二十余种，游客可自助采摘，按重计费。",
     "tags": ["自助采摘", "20+品种", "四季供应"], "location": "农场E区·大棚片区"},
]

ADOPTION_PLANS = [
    {"id": 1, "title": "稻田认养 · 一季稻（10㎡）", "emoji": "🌾",
     "image_url": f"{_IMG}/adopt_rice.jpg",
     "price": 299, "duration": "6个月", "stock": 20,
     "desc": "认养10平方米稻田，全程可远程查看生长直播，收获季寄送3kg新米，附溯源二维码。",
     "includes": ["专属地块挂牌", "生长周报推送", "收获寄送3kg", "溯源证书"]},
    {"id": 2, "title": "果树认养 · 苹果树（1棵）", "emoji": "🍎",
     "image_url": f"{_IMG}/adopt_apple.jpg",
     "price": 399, "duration": "1年", "stock": 15,
     "desc": "认养一棵苹果树，挂专属认养牌，秋季可来农场亲自采摘，或由农场代摘快递到家。",
     "includes": ["专属挂牌", "开花期照片", "采摘体验1次", "新鲜苹果10kg"]},
    {"id": 3, "title": "土鸡认养 · 散养土鸡（1只）", "emoji": "🐓",
     "image_url": f"{_IMG}/adopt_chicken.jpg",
     "price": 188, "duration": "3个月", "stock": 30,
     "desc": "认养一只散养土鸡，纯粮喂养180天以上，到期由农场宰杀真空包装快递到家。",
     "includes": ["专属编号", "成长视频", "到期寄送整鸡", "饲养日记"]},
    {"id": 4, "title": "蔬菜地认养 · 季度套餐（5㎡）", "emoji": "🥬",
     "image_url": f"{_IMG}/adopt_veggie.jpg",
     "price": 199, "duration": "3个月", "stock": 25,
     "desc": "认养5平方米蔬菜地，农场代为种植管理，每月配送2次时令蔬菜组合，约5kg/次。",
     "includes": ["专属地块", "月配送×2次", "可到场采摘", "有机肥种植"]},
    {"id": 5, "title": "蜂箱认养 · 一箱百花蜜", "emoji": "🍯",
     "image_url": f"{_IMG}/adopt_bee.jpg",
     "price": 468, "duration": "1年", "stock": 10,
     "desc": "认养一个蜂箱，年末收获时寄送2瓶500g原蜜（百花蜜），附养蜂日记和检测报告。",
     "includes": ["专属蜂箱挂牌", "养蜂日记", "原蜜500g×2瓶", "质检报告"]},
    {"id": 6, "title": "黑猪认养 · 半头散养黑猪", "emoji": "🐷",
     "image_url": f"{_IMG}/adopt_pig.jpg",
     "price": 1280, "duration": "6个月", "stock": 8,
     "desc": "认养半头山地黑猪，纯粮饲养出栏，到期寄送猪肉礼盒约15kg，含多部位分割。",
     "includes": ["专属编号", "生长视频", "猪肉礼盒15kg", "溯源证书"]},
]

ACTIVITIES = [
    {"id": 1, "title": "草莓采摘体验", "emoji": "🍓",
     "image_url": f"{_IMG}/act_strawberry.jpg",
     "price_per_person": 58, "duration": "2小时", "min_persons": 1, "max_persons": 20,
     "desc": "进入草莓大棚，自助采摘新鲜草莓，可品尝，采摘量按500g计入票价，超出部分按斤计费。",
     "available_dates": ["周六", "周日", "法定节假日"],
     "tips": "建议穿着轻便，携带遮阳帽，儿童须家长陪同。"},
    {"id": 2, "title": "农耕文化研学体验", "emoji": "🌱",
     "image_url": f"{_IMG}/act_farming.jpg",
     "price_per_person": 128, "duration": "半天", "min_persons": 5, "max_persons": 30,
     "desc": "包含：农具认知、插秧/播种实操、有机农业知识讲解、农家午餐，适合亲子和学生团体。",
     "available_dates": ["周六", "周日"],
     "tips": "建议5人以上团体预约，请提前3天预约，穿着可弄脏的衣物。"},
    {"id": 3, "title": "农家菜烹饪课堂", "emoji": "🍳",
     "image_url": f"{_IMG}/act_cooking.jpg",
     "price_per_person": 98, "duration": "3小时", "min_persons": 2, "max_persons": 12,
     "desc": "由农场大厨指导，现摘蔬菜现做，学习3道农家特色菜，课后享用自己烹饪的美食。",
     "available_dates": ["周六上午", "周日上午"],
     "tips": "建议提前预约，每期限12人，请按时到场。"},
    {"id": 4, "title": "蜜蜂养殖科普参观", "emoji": "🐝",
     "image_url": f"{_IMG}/act_bee.jpg",
     "price_per_person": 35, "duration": "1小时", "min_persons": 1, "max_persons": 15,
     "desc": "专业养蜂师讲解蜜蜂习性、蜂巢结构、采蜜过程，可近距离观察（有防护），品尝原蜜。",
     "available_dates": ["每天上午"],
     "tips": "对蜂蜜过敏者请勿参加，儿童须由成人陪同。"},
    {"id": 5, "title": "亲子农场半日游", "emoji": "👨‍👩‍👧",
     "image_url": f"{_IMG}/act_family.jpg",
     "price_per_person": 168, "duration": "半天", "min_persons": 2, "max_persons": 40,
     "desc": "含：喂养小动物、蔬菜采摘、亲子农耕体验、农家午餐，小孩免票（身高120cm以下）。",
     "available_dates": ["周六", "周日", "法定节假日"],
     "tips": "儿童请穿运动鞋，建议携带换洗衣物。"},
    {"id": 6, "title": "秋收丰收节特别活动", "emoji": "🎃",
     "image_url": f"{_IMG}/act_harvest.jpg",
     "price_per_person": 88, "duration": "全天", "min_persons": 1, "max_persons": 100,
     "desc": "每年10-11月举办丰收节，包含稻田收割体验、农产品展览、美食节、文艺演出，老少皆宜。",
     "available_dates": ["10月-11月指定日期"],
     "tips": "请关注农场公告，提前预约可享8折优惠。"},
]


@router.get("/scenes",          summary="农场风景列表")
def get_scenes()    -> Dict[str, Any]: return {"scenes": FARM_SCENES}

@router.get("/adoption_plans",  summary="认养计划列表")
def adoption_plans()-> Dict[str, Any]: return {"plans": ADOPTION_PLANS}

@router.get("/activities",      summary="体验活动列表")
def get_activities()-> Dict[str, Any]: return {"activities": ACTIVITIES}


@router.post("/adopt", summary="提交认养申请")
def adopt(payload: dict, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)) -> Dict[str, Any]:
    plan_id = payload.get("plan_id")
    plan    = next((p for p in ADOPTION_PLANS if p["id"] == plan_id), None)
    if not plan:
        raise HTTPException(status_code=404, detail="认养计划不存在")
    order = AdoptionOrder(
        user_id=user.id, plan_id=plan_id, plan_title=plan["title"],
        amount=plan["price"], status=AdoptionStatus.ACTIVE,
        contact_name=payload.get("contact_name", user.username),
        contact_phone=payload.get("contact_phone", ""),
        remark=payload.get("remark", ""),
    )
    db.add(order); db.commit(); db.refresh(order)
    return {"ok": True, "order_id": order.id,
            "msg": f"认养成功！「{plan['title']}」已开始，期待与你共同守护这片绿色。",
            "plan": plan}


@router.get("/my_adoptions", summary="我的认养订单")
def my_adoptions(db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> Dict[str, Any]:
    orders = db.query(AdoptionOrder).filter(
        AdoptionOrder.user_id == user.id
    ).order_by(AdoptionOrder.created_at.desc()).all()
    return {"items": [
        {"id": o.id, "plan_title": o.plan_title, "amount": o.amount,
         "status": o.status.value, "contact_name": o.contact_name,
         "created_at": o.created_at.isoformat() if o.created_at else None}
        for o in orders
    ]}


@router.get("/all_adoptions", summary="全部认养订单（农户/管理员）")
def all_adoptions(db: Session = Depends(get_db),
                  user: User = Depends(require_role("farmer", "admin"))) -> Dict[str, Any]:
    orders = db.query(AdoptionOrder).order_by(AdoptionOrder.created_at.desc()).all()
    return {"items": [
        {"id": o.id, "user_id": o.user_id, "plan_title": o.plan_title,
         "amount": o.amount, "status": o.status.value,
         "contact_name": o.contact_name, "contact_phone": o.contact_phone,
         "remark": o.remark,
         "created_at": o.created_at.isoformat() if o.created_at else None}
        for o in orders
    ]}


@router.post("/adoption/{order_id}/complete", summary="完成认养")
def complete_adoption(order_id: int, db: Session = Depends(get_db),
                      user: User = Depends(require_role("farmer", "admin"))) -> Dict[str, Any]:
    order = db.query(AdoptionOrder).filter(AdoptionOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    order.status = AdoptionStatus.COMPLETED
    db.commit()
    return {"ok": True, "msg": "已标记为完成"}


@router.post("/book_activity", summary="预约体验活动")
def book_activity(payload: dict, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> Dict[str, Any]:
    activity_id  = payload.get("activity_id")
    participants = int(payload.get("participants", 1))
    activity     = next((a for a in ACTIVITIES if a["id"] == activity_id), None)
    if not activity:
        raise HTTPException(status_code=404, detail="活动不存在")
    if participants < activity["min_persons"]:
        raise HTTPException(status_code=400, detail=f"最少需要{activity['min_persons']}人")
    if participants > activity["max_persons"]:
        raise HTTPException(status_code=400, detail=f"最多支持{activity['max_persons']}人")
    booking = ActivityBooking(
        user_id=user.id, activity_id=activity_id,
        activity_title=activity["title"],
        activity_date=payload.get("activity_date", ""),
        participants=participants,
        contact_name=payload.get("contact_name", user.username),
        contact_phone=payload.get("contact_phone", ""),
        amount=activity["price_per_person"] * participants,
        status="confirmed",
    )
    db.add(booking); db.commit(); db.refresh(booking)
    return {"ok": True, "booking_id": booking.id,
            "msg": f"预约成功！「{activity['title']}」已确认。",
            "amount": booking.amount}


@router.get("/my_bookings", summary="我的活动预约")
def my_bookings(db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> Dict[str, Any]:
    bookings = db.query(ActivityBooking).filter(
        ActivityBooking.user_id == user.id
    ).order_by(ActivityBooking.created_at.desc()).all()
    return {"items": [
        {"id": b.id, "activity_title": b.activity_title,
         "activity_date": b.activity_date, "participants": b.participants,
         "amount": b.amount, "status": b.status,
         "created_at": b.created_at.isoformat() if b.created_at else None}
        for b in bookings
    ]}