from dataclasses import dataclass
from pathlib import Path

from omegaconf import OmegaConf
from dotenv import load_dotenv


@dataclass
class FileConfig:
    enable: bool
    level: str
    path: str
    rotation: str
    retention: str


@dataclass
class ConsoleConfig:
    enable: bool
    level: str


@dataclass
class LoggingConfig:
    file: FileConfig
    console: ConsoleConfig


@dataclass
class DBConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


@dataclass
class QdrantConfig:
    host: str
    port: int
    embedding_size: int


@dataclass
class EmbeddingConfig:
    host: str
    port: int
    model: str


@dataclass
class ESConfig:
    host: str
    port: int
    index_name: str


@dataclass
class LLMConfig:
    model_name: str
    api_key: str
    base_url: str


@dataclass
class AppConfig:
    logging: LoggingConfig
    db_meta: DBConfig
    db_dw: DBConfig
    qdrant: QdrantConfig
    embedding: EmbeddingConfig
    es: ESConfig
    llm: LLMConfig


def _load_app_config() -> AppConfig:
    # 先显式加载项目根目录下的 `.env`。
    #
    # 这个项目的大部分配置都通过 `oc.env` 从环境变量读取，例如：
    # - OPENAI_API_KEY
    # - OPENAI_BASE_URL
    # - META_DB_HOST
    # - ES_HOST
    #
    # 如果只是在本地直接执行：
    # `uv run python -m app.agent.graph`
    # shell 并不会自动把 `.env` 注入到当前进程环境里。这样一来，
    # OmegaConf 在解析 `${oc.env:...}` 时就会回退到默认值，最终可能导致：
    # - API key 为空
    # - base_url 落到默认代理地址
    # - 数据库/ES/Qdrant 地址不是预期值
    #
    # 因此这里在读取 YAML 前先把 `.env` 加载到进程环境中，保证：
    # - 本地命令行运行
    # - pytest
    # - 单独调试 graph/main
    # 这些场景都能和 Docker / compose 使用同一份配置来源。
    project_root = Path(__file__).parents[2]
    load_dotenv(project_root / ".env", override=False)

    conf_dir = Path(__file__).parents[2] / "conf"
    config_path = conf_dir / "app_config.yaml"
    if not config_path.exists():
        config_path = conf_dir / "app_config.yaml.example"

    schema = OmegaConf.structured(AppConfig)
    context = OmegaConf.load(config_path)
    config = OmegaConf.merge(schema, context)
    OmegaConf.resolve(config)
    return OmegaConf.to_object(config)


app_config = _load_app_config()
