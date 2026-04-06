from qdrant_client import AsyncQdrantClient

from app.conf.app_config import QdrantConfig, app_config


class QdrantClientManager:
    def __init__(self, qdrant_config: QdrantConfig):
        self.qdrant_config = qdrant_config
        self.client: AsyncQdrantClient | None = None

    def init(self) -> None:
        if self.client is not None:
            return
        if self.qdrant_config.host in {"memory", ":memory:"}:
            self.client = AsyncQdrantClient(location=":memory:")
        else:
            self.client = AsyncQdrantClient(
                url=f"http://{self.qdrant_config.host}:{self.qdrant_config.port}"
            )

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()
            self.client = None


qdrant_client_manager = QdrantClientManager(app_config.qdrant)
