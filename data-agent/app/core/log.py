import sys
from pathlib import Path

from loguru import logger as _logger

from app.conf.app_config import app_config
from app.core.context import request_id_ctx_var


def _inject_request_id(record: dict) -> None:
    record["extra"]["request_id"] = request_id_ctx_var.get()


log_format = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<magenta>request_id={extra[request_id]}</magenta> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

logger = _logger.patch(_inject_request_id)
logger.remove()

if app_config.logging.console.enable:
    logger.add(sys.stdout, level=app_config.logging.console.level, format=log_format)

if app_config.logging.file.enable:
    log_dir = Path(app_config.logging.file.path)
    if not log_dir.is_absolute():
        log_dir = Path(__file__).parents[2] / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "app.log",
        level=app_config.logging.file.level,
        format=log_format,
        rotation=app_config.logging.file.rotation,
        retention=app_config.logging.file.retention,
        encoding="utf-8",
    )
