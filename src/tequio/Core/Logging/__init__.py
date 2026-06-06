"""Setup de logging (Loguru + intercept del stdlib `logging`). Re-exporta la
función de configuración Y el formato de logs (que `Core/Cron` consume para
sus sinks per-cron).
"""

from __future__ import annotations

from tequio.Core.Logging.Logging import _LOG_FORMAT, setup_logging

__all__ = ["_LOG_FORMAT", "setup_logging"]
