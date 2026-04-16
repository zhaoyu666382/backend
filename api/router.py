from fastapi import APIRouter
from routers import auth, products, batches, trace, orders, admin, recommendations, pest, agritourism

api_router = APIRouter(prefix="/api")

api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(products.router, prefix="/products", tags=["产品"])
api_router.include_router(batches.router, prefix="/batches", tags=["批次"])
api_router.include_router(trace.router, prefix="/trace", tags=["溯源"])
api_router.include_router(orders.router, prefix="/orders", tags=["订单"])
api_router.include_router(admin.router, prefix="/admin", tags=["管理"])
api_router.include_router(recommendations.router, prefix="/recommendations", tags=["推荐"])
api_router.include_router(pest.router, prefix="/pest", tags=["病虫识别"])
api_router.include_router(agritourism.router, prefix="/agritourism", tags=["农旅"])
