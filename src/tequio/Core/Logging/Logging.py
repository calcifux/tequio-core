"""Logging con Loguru: consola + archivo rotativo/comprimido/async, y captura
del logging estándar (celery) vía InterceptHandler.
"""

from __future__ import annotations

import logging
import sys
from types import FrameType

from loguru import logger

from tequio.Core.Config import settings

_LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {name} | {message}"
_configured = False


class _InterceptHandler(logging.Handler):
    """Redirige los registros del logging ESTÁNDAR hacia Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame: FrameType | None = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(level: str | None = None, json_file: bool | None = None) -> None:
    global _configured
    if _configured:
        return
    _configured = True

    level = level or settings.log_level
    json_file = settings.log_json if json_file is None else json_file
    text_log_file = f"{settings.log_dir}/app.log"
    json_log_file = f"{settings.log_dir}/app.jsonl"

    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format=_LOG_FORMAT,
        enqueue=True,
        backtrace=True,
        # diagnose añade los VALORES de las variables al traceback (útil al depurar, pero FUGA
        # datos —tokens, passwords— en consola). Solo en local; en qa/prod, off (el archivo igual).
        diagnose=settings.app_env == "local",
    )
    logger.add(
        text_log_file,
        level=level,
        format=_LOG_FORMAT,
        rotation="00:00",
        retention="14 days",
        compression="zip",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )
    if json_file:
        logger.add(
            json_log_file,
            level=level,
            serialize=True,
            rotation="00:00",
            retention="14 days",
            compression="zip",
            enqueue=True,
            backtrace=True,
            diagnose=False,
        )

    logging.basicConfig(handlers=[_InterceptHandler()], level=logging.INFO, force=True)
    for name in ("celery",):
        standard_logger = logging.getLogger(name)
        standard_logger.handlers = [_InterceptHandler()]
        standard_logger.propagate = False
