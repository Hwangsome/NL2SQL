import httpx
from typing import Protocol

from app.conf.app_config import EmbeddingConfig, app_config


class EmbeddingClientProtocol(Protocol):
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def aembed_query(self, text: str) -> list[float]: ...


class CompatibleEmbeddingClient:
    """基于 OpenAI 兼容协议的 embedding 客户端。

    为什么这里不直接继续使用 `LangChain` 的 `OpenAIEmbeddings`：
    - 本项目现在需要兼容 DashScope 的 `/compatible-mode/v1/embeddings`
    - 实测 `LangChain` 在 embedding 调用链路里会额外做一层输入处理
    - 这层处理会让 DashScope 返回 `InvalidParameter`
    - 但 DashScope 官方兼容文档本身支持直接调用 `/embeddings`
    - 因此这里改成最薄的一层 HTTP 客户端，直接按兼容协议发请求

    这样做的好处是：
    - 对 OpenAI 官方接口可用
    - 对 DashScope 兼容接口也可用
    - 请求体完全可控，便于后续排查模型兼容问题
    """

    def __init__(self, base_url: str, api_key: str, model: str, dimensions: int, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """把一批文本转成向量。

        注意：
        - OpenAI 兼容接口和 DashScope 兼容接口都要求 `input` 是字符串或字符串数组
        - DashScope 官方文档中，`text-embedding-v4` 单次最多支持 10 条文本
        - 因此这里按 10 条切批，避免知识库构建时一次提交过多文本而失败
        """

        if not texts:
            return []

        vectors: list[list[float]] = []
        batch_size = 10
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            response = await self._client.post(
                f"{self.base_url}/embeddings",
                json={
                    "model": self.model,
                    "input": batch if len(batch) > 1 else batch[0],
                    "dimensions": self.dimensions,
                    "encoding_format": "float",
                },
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data", [])
            vectors.extend(item.get("embedding", []) for item in data)
        return vectors

    async def aembed_query(self, text: str) -> list[float]:
        """把单条查询文本转成向量。"""

        embeddings = await self.aembed_documents([text])
        return embeddings[0]

    async def aclose(self) -> None:
        await self._client.aclose()


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
            # 这里的 `openai` 实际表示“使用 OpenAI 兼容协议的 embedding 服务”，
            # 不限定后端供应商一定是 OpenAI 官方。
            #
            # 当前项目会把这一层同时用于：
            # - OpenAI 官方 `/v1/embeddings`
            # - DashScope `/compatible-mode/v1/embeddings`
            #
            # 因此采用自定义的最小兼容客户端，确保请求体对不同兼容服务都可控。
            self.client = CompatibleEmbeddingClient(
                base_url=app_config.llm.base_url,
                api_key=app_config.llm.api_key,
                model=self.embedding_config.model,
                dimensions=app_config.qdrant.embedding_size,
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
