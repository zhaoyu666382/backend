from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import settings
from models import Base

# 创建数据库引擎
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    echo=settings.DEBUG
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """
    获取数据库会话
    依赖注入使用
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """
    初始化数据库
    创建所有表
    """
    Base.metadata.create_all(bind=engine)
    print("✅ 数据库表创建成功")

def drop_db():
    """
    删除所有表
    警告：会删除所有数据
    """
    Base.metadata.drop_all(bind=engine)
    print("⚠️  数据库表已删除")

if __name__ == "__main__":
    # 初始化数据库
    init_db()
