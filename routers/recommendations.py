from typing import Dict, Any, List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import time

from core.deps import get_db, get_current_user
from models import Product, ProductView, Order, OrderItem, User

router = APIRouter()


# =========================
# 工具函数：格式化返回
# =========================
def _format_products(products, reason: str, score_map=None):
    result = []
    for p in products:
        item = {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "price": p.price,
            "unit": p.unit,
            "stock": p.stock,
            "image_url": p.image_url,
            "origin": p.origin,
            "organic_certified": p.organic_certified,
            "description": p.description,
            "reason": reason,
        }
        if score_map:
            item["score"] = score_map.get(p.id, 0)
        result.append(item)
    return result


# =========================
# 规则推荐（兜底，100%成功）
# =========================
def _rule_recommend(user: User, db: Session, limit=6):
    """
    升级版推荐：
    1. 买过 > 浏览过 > 其他
    2. 严格按偏好排序（不再乱）
    """

    try:
        # =========================
        # 1️⃣ 统计偏好权重
        # =========================
        weight = {}

        # 买过（权重3）
        bought = db.query(Product.category).join(
            OrderItem, OrderItem.product_id == Product.id
        ).join(
            Order, Order.user_id == user.id
        ).filter(Product.is_active == True).all()

        for r in bought:
            if r[0]:
                weight[r[0]] = weight.get(r[0], 0) + 3

        # 浏览过（权重2）
        viewed = db.query(Product.category).join(
            ProductView, ProductView.product_id == Product.id
        ).filter(
            ProductView.user_id == user.id,
            Product.is_active == True
        ).all()

        for r in viewed:
            if r[0]:
                weight[r[0]] = weight.get(r[0], 0) + 2

        # =========================
        # 2️⃣ 获取所有商品
        # =========================
        products = db.query(Product).filter(
            Product.is_active == True
        ).all()

        # =========================
        # 3️⃣ 按权重排序（核心）
        # =========================
        products.sort(
            key=lambda p: weight.get(p.category, 0),
            reverse=True
        )

        # =========================
        # 4️⃣ 截取前N个
        # =========================
        products = products[:limit]

        # =========================
        # 5️⃣ 推荐理由
        # =========================
        top_cats = sorted(weight, key=weight.get, reverse=True)

        if top_cats:
            reason = f"优先推荐你常浏览/购买的：{'、'.join(top_cats[:2])}"
        else:
            reason = "为你推荐热门绿色食品"

        return [
            {
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "price": p.price,
                "unit": p.unit,
                "stock": p.stock,
                "image_url": p.image_url,
                "origin": p.origin,
                "organic_certified": p.organic_certified,
                "description": p.description,
                "reason": reason
            }
            for p in products
        ]

    except Exception as e:
        print(f"[Recommend] 规则推荐错误：{e}")
        return []


# =========================
# 主接口
# =========================
@router.get("/", summary="个性化推荐")
def list_recommendations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = 6,
) -> Dict[str, Any]:

    start_time = time.time()

    # =========================
    # 尝试 AI 模型推荐
    # =========================
    try:
        from ai.rec_model import get_recommendations

        viewed = [
            r[0] for r in
            db.query(ProductView.product_id)
            .filter(ProductView.user_id == user.id)
            .order_by(ProductView.viewed_at.desc())
            .limit(20).all()
        ]

        all_items = [
            r[0] for r in
            db.query(Product.id)
            .filter(Product.is_active == True)
            .all()
        ]

        # 🚨 超时保护（关键）
        if time.time() - start_time > 1.5:
            raise TimeoutError("推荐计算超时")

        recs = get_recommendations(user.id, viewed, all_items, limit)

        if recs:
            score_map = {
                r["item_id"]: r.get("score", 0)
                for r in recs
            }

            ids = [r["item_id"] for r in recs]

            products = db.query(Product).filter(
                Product.id.in_(ids),
                Product.is_active == True
            ).all()

            # 按模型分数排序
            products.sort(
                key=lambda p: score_map.get(p.id, 0),
                reverse=True
            )

            print("[Recommend] 使用 AI 推荐")

            return {
                "items": _format_products(
                    products,
                    reason="AI个性化推荐",
                    score_map=score_map
                ),
                "source": "ai-model"
            }

    except Exception as e:
        print(f"[Recommend] AI失败，降级规则引擎：{e}")

    # =========================
    # 规则推荐（兜底）
    # =========================
    items = _rule_recommend(user, db, limit)

    print("[Recommend] 使用规则推荐")

    return {
        "items": items,
        "source": "rule-engine"
    }