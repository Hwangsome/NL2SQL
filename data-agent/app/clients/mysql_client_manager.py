from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.conf.app_config import DBConfig, app_config


class MysqlClientManager:
    def __init__(self, db_config: DBConfig):
        self.db_config = db_config
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None

    def _get_url(self) -> str:
        return (
            f"mysql+asyncmy://{self.db_config.user}:{self.db_config.password}"
            f"@{self.db_config.host}:{self.db_config.port}/{self.db_config.database}"
            "?charset=utf8mb4"
        )

    def init(self) -> None:
        if self.engine is not None:
            return
        self.engine = create_async_engine(
            self._get_url(),
            pool_size=10,
            pool_pre_ping=True,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            autoflush=True,
            expire_on_commit=False,
            autobegin=True,
        )

    async def close(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None

    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        if self.session_factory is None:
            raise RuntimeError("MySQL client manager is not initialized.")
        async with self.session_factory() as session:
            yield session


meta_mysql_client_manager = MysqlClientManager(app_config.db_meta)
dw_mysql_client_manager = MysqlClientManager(app_config.db_dw)
