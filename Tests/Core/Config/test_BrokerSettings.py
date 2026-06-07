"""Config broker-agnostic: las properties effective_* resuelven broker/backend/lock
con los fallbacks correctos, y visibility_timeout solo aplica a redis/SQS.
"""

from __future__ import annotations

from tequio.Core.Config.Settings import Settings


def test_broker_falls_back_to_local_redis_when_empty() -> None:
    assert Settings(broker_url="").effective_broker_url == "redis://localhost:6379/0"


def test_broker_uses_explicit_url() -> None:
    s = Settings(broker_url="amqp://guest:guest@localhost:5672//")
    assert s.effective_broker_url == "amqp://guest:guest@localhost:5672//"


def test_lock_falls_back_to_local_redis_when_empty() -> None:
    assert Settings(lock_url="").effective_lock_url == "redis://localhost:6379/0"


def test_result_backend_is_none_by_default() -> None:
    assert Settings(result_backend_url="").effective_result_backend is None


def test_visibility_timeout_only_for_redis_and_sqs() -> None:
    assert Settings(broker_url="redis://r/0").broker_uses_visibility_timeout is True
    assert Settings(broker_url="sqs://k:s@").broker_uses_visibility_timeout is True
    assert Settings(broker_url="amqp://guest@localhost//").broker_uses_visibility_timeout is False


def test_queue_namespace_defaults_empty() -> None:
    """Default vacío = comportamiento de siempre (sin prefijo de colas), 100% retrocompatible."""
    assert Settings().queue_namespace == ""


def test_queue_namespace_reads_explicit_value() -> None:
    """Se puede fijar (env QUEUE_NAMESPACE) para convivir en un broker compartido."""
    assert Settings(queue_namespace="miapp").queue_namespace == "miapp"
