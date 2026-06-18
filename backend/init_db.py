"""
数据库初始化脚本
创建所有表结构
"""
from models.user import Base
from core.database import engine

def init_db():
    """创建所有数据库表"""
    print("开始创建数据库表...")
    Base.metadata.create_all(bind=engine)
    print("数据库表创建完成！")

if __name__ == "__main__":
    init_db()
