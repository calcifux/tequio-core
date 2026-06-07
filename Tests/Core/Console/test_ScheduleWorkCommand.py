"""Tests del command `schedule work` — el argv con que arranca beat.

No levantamos Celery: monkeypatcheamos `celery_app.start` para CAPTURAR el argv.
Protege que `--schedule-file` se traduzca a `-s <ruta>` (dónde persiste beat su
calendario) y que sin la opción NO se añada (default ./celerybeat-schedule del CWD).
"""

from __future__ import annotations

from typing import Any

from pytest import MonkeyPatch

from tequio.Core.CeleryApp import celery_app
from tequio.Core.Console.Commands.ScheduleWorkCommand import schedule_work


def _capture_argv(monkeypatch: MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(celery_app, "start", lambda argv: captured.update(argv=argv))
    return captured


def test_sin_schedule_file_no_anade_flag(monkeypatch: MonkeyPatch) -> None:
    captured = _capture_argv(monkeypatch)

    schedule_work(loglevel="INFO", schedule_file=None)

    assert captured["argv"] == ["beat", "--loglevel", "INFO"]
    assert "-s" not in captured["argv"]  # default: ./celerybeat-schedule del CWD


def test_schedule_file_viaja_como_dash_s(monkeypatch: MonkeyPatch) -> None:
    captured = _capture_argv(monkeypatch)

    schedule_work(loglevel="WARNING", schedule_file="/tmp/celerybeat-schedule")

    assert captured["argv"] == ["beat", "--loglevel", "WARNING", "-s", "/tmp/celerybeat-schedule"]
