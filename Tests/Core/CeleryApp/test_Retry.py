"""Tests del helper `retry_policy`: defaults desde .env y override A MANO en código."""

from __future__ import annotations

from tequio.Core.CeleryApp import retry_policy
from tequio.Core.Config import settings


def test_retry_policy_uses_env_defaults() -> None:
    """Sin argumentos numéricos, toma los defaults framework-wide de Settings (.env)."""
    policy = retry_policy(retry_for=(ConnectionError,))

    assert policy["autoretry_for"] == (ConnectionError,)
    assert policy["max_retries"] == settings.task_max_retries
    assert policy["retry_backoff"] == settings.task_retry_backoff
    assert policy["retry_backoff_max"] == settings.task_retry_backoff_max
    assert policy["retry_jitter"] is True


def test_retry_policy_explicit_args_override_env() -> None:
    """Los argumentos explícitos pisan el .env por-task, sin tocar el entorno."""
    policy = retry_policy(
        retry_for=(TimeoutError, ConnectionError),
        max_retries=7,
        backoff=10,
        backoff_max=120,
        jitter=False,
    )

    assert policy["autoretry_for"] == (TimeoutError, ConnectionError)
    assert policy["max_retries"] == 7
    assert policy["retry_backoff"] == 10
    assert policy["retry_backoff_max"] == 120
    assert policy["retry_jitter"] is False


def test_retry_policy_backoff_can_be_disabled() -> None:
    """`backoff=False` desactiva el backoff exponencial (countdown fijo de Celery)."""
    policy = retry_policy(retry_for=(ConnectionError,), backoff=False)

    assert policy["retry_backoff"] is False
