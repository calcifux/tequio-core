"""Scheduler estilo Laravel: el decorador `cron_task` + los helpers de cadencia
(`every_minute()`, `daily_at()`, ...) + el registro de crons que consume
`schedule run`. Re-exportado para `from tequio.Core.Cron import cron_task, daily_at`.
"""

from __future__ import annotations

from tequio.Core.Cron.Cron import (
    RegisteredCron,
    cron_task,
    registered_crons,
    reset_cron_registry,
)
from tequio.Core.Cron.Schedule import (
    cron,
    daily,
    daily_at,
    every_fifteen_minutes,
    every_five_minutes,
    every_minute,
    every_minutes,
    every_ten_minutes,
    every_thirty_minutes,
    hourly,
    hourly_at,
    monthly,
    to_crontab,
    weekly,
)

__all__ = [
    "RegisteredCron",
    "cron",
    "cron_task",
    "daily",
    "daily_at",
    "every_fifteen_minutes",
    "every_five_minutes",
    "every_minute",
    "every_minutes",
    "every_ten_minutes",
    "every_thirty_minutes",
    "hourly",
    "hourly_at",
    "monthly",
    "registered_crons",
    "reset_cron_registry",
    "to_crontab",
    "weekly",
]
