from elasticsearch import AsyncElasticsearch

from app.conf.app_config import app_config
from app.entities.value_info import ValueInfo


class ValueESRepository:
    def __init__(self, client: AsyncElasticsearch):
        self.client = client
        self.index_name = app_config.es.index_name

    async def ensure_index(self) -> None:
        exists = await self.client.indices.exists(index=self.index_name)
        if not exists:
            await self.client.indices.create(
                index=self.index_name,
                mappings={
                    "properties": {
                        "id": {"type": "keyword"},
                        "value": {"type": "text"},
                        "column_id": {"type": "keyword"},
                    }
                },
            )

    async def index(self, value_infos: list[ValueInfo]) -> None:
        if not value_infos:
            return
        for value_info in value_infos:
            await self.client.index(index=self.index_name, id=value_info.id, document=value_info.__dict__)
        await self.client.indices.refresh(index=self.index_name)

    async def search(self, keyword: str, score_threshold: float = 0.6, limit: int = 5) -> list[ValueInfo]:
        result = await self.client.search(
            index=self.index_name,
            query={"match": {"value": keyword}},
            min_score=score_threshold,
            size=limit,
        )
        return [ValueInfo(**hit["_source"]) for hit in result["hits"]["hits"]]
