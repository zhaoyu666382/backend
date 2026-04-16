import os
import sys
import logging
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Ensure project root is importable (for ../blockchain)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from config import settings  # noqa: E402
from database import init_db, SessionLocal  # noqa: E402
from seed import seed_default_accounts, seed_demo_data  # noqa: E402
from api.router import api_router  # noqa: E402

# Logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("green-food-api")

app = FastAPI(
    title="绿色食品交易平台接口",
    description="FastAPI + SQLite + 区块链模拟",
    version=settings.VERSION,
)


# ── 添加到 app.py 中 FastAPI() 初始化之后 ─────────────────────────────

@app.on_event("startup")
async def startup_preload():
    """
    后端启动时自动预加载两个 AI 模型到内存
    这样用户第一次请求时不需要等待模型加载（冷启动延迟从 3-5s 降至 0.2s 以内）
    """
    import asyncio

    loop = asyncio.get_event_loop()

    # 预加载病虫害识别模型
    try:
        await loop.run_in_executor(None, _preload_pest)
    except Exception as e:
        print(f"[Startup] 病虫害模型预加载跳过：{e}")

    # 预加载推荐模型
    try:
        await loop.run_in_executor(None, _preload_rec)
    except Exception as e:
        print(f"[Startup] 推荐模型预加载跳过：{e}")


def _preload_pest():
    try:
        from ai.pest_model import preload
        preload()
    except Exception as e:
        print(f"[Startup] 病虫害模型：{e}")


def _preload_rec():
    try:
        from ai.rec_model import preload
        preload()
    except Exception as e:
        print(f"[Startup] 推荐模型：{e}")

# CORS（跨域）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态资源（上传文件/图片）
# 访问方式：http://localhost:8000/static/<filename>
app.mount("/static", StaticFiles(directory=str(settings.UPLOAD_DIR)), name="static")


@app.on_event("startup")
def on_startup():
    # 1) 自动创建表
    init_db()

    # 2) 自动初始化演示账号 + 测试数据
    db = SessionLocal()
    try:
        seed_default_accounts(db)
        seed_demo_data(db)
    finally:
        db.close()

    logger.info("✅ Database initialized & demo data seeded")


@app.get("/health", tags=["系统"])
def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "service": settings.APP_NAME,
        "version": settings.VERSION,
    }


@app.get("/", tags=["系统"])
def root():
    return {"message": "绿色食品交易平台接口", "docs": "/docs", "health": "/health"}


# 所有业务接口统一前缀 /api
app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
