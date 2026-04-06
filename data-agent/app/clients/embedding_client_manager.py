import httpx
from typing import Protocol

from langchain_openai import OpenAIEmbeddings

from app.conf.app_config import EmbeddingConfig, app_config


class EmbeddingClientProtocol(Protocol):
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def aembed_query(self, text: str) -> list[float]: ...


class TEIEmbeddingClient:
    def __init__(self, base_url: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._client.post(f"{self.base_url}/embed", json={"inputs": texts})
        response.raise_for_status()
        return response.json()

    async def aembed_query(self, text: str) -> list[float]:
        embeddings = await self.aembed_documents([text])
        return embeddings[0]

    async def aclose(self) -> None:
        await self._client.aclose()


class EmbeddingClientManager:
    def __init__(self, embedding_config: EmbeddingConfig):
        self.embedding_config = embedding_config
        self.client: EmbeddingClientProtocol | None = None

    def _get_url(self) -> str:
        return f"http://{self.embedding_config.host}:{self.embedding_config.port}"

    def init(self) -> None:
        if self.client is not None:
            return
        if self.embedding_config.host == "openai":
            self.client = OpenAIEmbeddings(
                model=self.embedding_config.model,
                dimensions=app_config.qdrant.embedding_size,
                api_key=app_config.llm.api_key,
                base_url=app_config.llm.base_url,
            )
        else:
            self.client = TEIEmbeddingClient(self._get_url())

    async def close(self) -> None:
        if self.client is None:
            return
        aclose = getattr(self.client, "aclose", None)
        if callable(aclose):
            await aclose()
        self.client = None


embedding_client_manager = EmbeddingClientManager(app_config.embedding)
