from dataclasses import asdict

from qdrant_client import AsyncQdrantClient, models

from app.conf.app_config import app_config
from app.entities.metric_info import MetricInfo


class MetricQdrantRepository:
    def __init__(self, client: AsyncQdrantClient):
        self.client = client
        self.collection_name = "metric_info"

    async def ensure_collection(self) -> None:
        collections = await self.client.get_collections()
        names = {collection.name for collection in collections.collections}
        if self.collection_name not in names:
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=app_config.qdrant.embedding_size,
                    distance=models.Distance.COSINE,
                ),
            )

    async def upsert(self, ids: list[str], vectors: list[list[float]], payloads: list[MetricInfo]) -> None:
        points = [
            models.PointStruct(id=point_id, vector=vector, payload=asdict(payload))
            for point_id, vector, payload in zip(ids, vectors, payloads, strict=True)
        ]
        if points:
            await self.client.upsert(collection_name=self.collection_name, points=points)

    async def search(
        self,
        query_vector: list[float],
        score_threshold: float = 0.6,
        limit: int = 5,
    ) -> list[MetricInfo]:
        result = await self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            score_threshold=score_threshold,
            limit=limit,
        )
        return [MetricInfo(**(point.payload or {})) for point in result.points if point.payload]
