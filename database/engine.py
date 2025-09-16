from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DB_FILE = "jobs.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_FILE}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
