"""pytest 全局 fixture - 提供测试用 DB engine、Session 与 httpx AsyncClient"""
import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, get_db
from main import app


@pytest.fixture
def test_engine():
    """内存 SQLite engine,每个测试函数独立,零文件 IO。

    用 StaticPool 保证同一连接被复用(check_same_thread=False + 内存库需共享连接)。
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def test_db(test_engine):
    """测试用 Session,自动回滚清理,不污染其他用例"""
    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    db = TestSession()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest_asyncio.fixture
async def client(test_db):
    """httpx AsyncClient,覆盖 get_db 依赖注入测试 session。

    所有 API 请求使用内存 SQLite,不触碰真实数据库。
    """
    def _override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    import httpx
    async with httpx.AsyncClient(app=app, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
