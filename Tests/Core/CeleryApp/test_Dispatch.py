"""Tests del guard del broker (error limpio cuando redis no está)."""

from __future__ import annotations

import pytest
import redis.exceptions
from kombu.exceptions import OperationalError

from tequio.Core.CeleryApp import QueueUnavailableError, broker_guard


def test_broker_guard_converts_kombu_operational_error() -> None:
    with pytest.raises(QueueUnavailableError, match="redis"):
        with broker_guard():
            raise OperationalError("broker caído")


def test_broker_guard_converts_redis_connection_error() -> None:
    with pytest.raises(QueueUnavailableError):
        with broker_guard():
            raise redis.exceptions.ConnectionError("no connection")


def test_broker_guard_lets_other_errors_through() -> None:
    # No debe tragarse errores ajenos al broker (p. ej. un bug de programación).
    with pytest.raises(ValueError):
        with broker_guard():
            raise ValueError("otro error")
