from elasticsearch import AsyncElasticsearch

from app.conf.app_config import ESConfig, app_config


class ESClientManager:
    def __init__(self, es_config: ESConfig):
        self.es_config = es_config
        self.client: AsyncElasticsearch | None = None

    def _get_url(self) -> str:
        return f"http://{self.es_config.host}:{self.es_config.port}"

    def init(self) -> None:
        if self.client is None:
            self.client = AsyncElasticsearch(self._get_url())

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()
            self.client = None


es_client_manager = ESClientManager(app_config.es)
