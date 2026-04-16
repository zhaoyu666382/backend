"""
数据库初始化脚本（可选）
- 自动创建表
- 自动插入演示账号/测试数据
用法：
    python -m scripts.init_db
"""

from database import init_db, SessionLocal
from seed import seed_default_accounts, seed_demo_data


def main():
    init_db()
    db = SessionLocal()
    try:
        seed_default_accounts(db)
        seed_demo_data(db)
    finally:
        db.close()
    print("✅ init_db done")


if __name__ == "__main__":
    main()
