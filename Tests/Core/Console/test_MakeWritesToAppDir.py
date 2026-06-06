"""Guardrail: `make:*` debe escribir en el código del USUARIO (settings.app_dir),
NO en el paquete tequio instalado.

Regresión real: tras la Fase A, `make model` usaba `Path(__file__).parents[3]` y escribía
en `src/tequio/Models/` (el framework) en vez del `app/Models/` del proyecto. Este test lo
fija: monkeypatchea `app_dir` a un tmp y verifica que el archivo cae ahí.
"""

from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

import tequio.Core.Console.Commands.MakeCommands as make_mod
from tequio.Core.Config import settings


def test_make_model_writes_to_app_dir(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_dir", str(tmp_path / "app"))

    make_mod.make_model("Widget")

    assert (tmp_path / "app" / "Models" / "Widget.py").is_file(), (
        "make model debe escribir en settings.app_dir/Models, no en el paquete tequio"
    )


def test_make_observer_writes_to_app_dir(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_dir", str(tmp_path / "app"))

    make_mod.make_observer("Tasks", "NotifyAdmin")

    assert (tmp_path / "app" / "Modules" / "Tasks" / "Observers" / "NotifyAdminObserver.py").is_file()


def test_make_handler_writes_to_app_dir(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_dir", str(tmp_path / "app"))

    make_mod.make_handler("Tasks", "CompleteTask")

    assert (tmp_path / "app" / "Modules" / "Tasks" / "Handlers" / "CompleteTaskHandler.py").is_file()


def test_make_repository_writes_to_app_dir(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_dir", str(tmp_path / "app"))

    make_mod.make_repository("Tasks", "Task")

    base = tmp_path / "app" / "Modules" / "Tasks" / "Repositories"
    assert (base / "TaskRepository.py").is_file()
    assert (base / "__init__.py").is_file()  # _ensure_pkg


def test_make_pipe_writes_to_app_dir(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_dir", str(tmp_path / "app"))

    make_mod.make_pipe("Tasks", "NormalizeTitle")

    assert (tmp_path / "app" / "Modules" / "Tasks" / "Pipes" / "NormalizeTitle.py").is_file()


def test_make_mailable_writes_to_app_dir(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_dir", str(tmp_path / "app"))

    make_mod.make_mailable("Tasks", "TaskReady")

    target = tmp_path / "app" / "Modules" / "Tasks" / "Mail" / "TaskReadyMailable.py"
    assert target.is_file()
    assert (target.parent / "__init__.py").is_file()  # _ensure_pkg


def test_make_mailable_stub_assumes_the_emails_queue(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """El stub generado narra el despacho ENCOLADO a la cola de correos `emails` (convención
    Laravel `->onQueue('emails')`) y la consume con `queue work --queue emails`."""
    monkeypatch.setattr(settings, "app_dir", str(tmp_path / "app"))

    make_mod.make_mailable("Tasks", "TaskReady")

    content = (tmp_path / "app" / "Modules" / "Tasks" / "Mail" / "TaskReadyMailable.py").read_text(encoding="utf-8")
    assert 'queue="emails"' in content  # el ejemplo de despacho asume la cola emails
    assert "init_kwargs=" in content  # con init_kwargs que coincide con el __init__
    assert "queue work --queue emails" in content  # y cómo consumirla
    assert "tasks/emails/" in content  # la plantilla apunta a Resources/Views/emails/ del módulo


def test_make_job_writes_to_app_dir(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_dir", str(tmp_path / "app"))

    make_mod.make_job("Tasks", "SendReport")

    assert (tmp_path / "app" / "Modules" / "Tasks" / "Jobs" / "SendReport.py").is_file()


def test_make_service_writes_to_app_dir(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_dir", str(tmp_path / "app"))

    make_mod.make_service("Tasks", "CompleteTask")

    base = tmp_path / "app" / "Modules" / "Tasks" / "Services"
    assert (base / "CompleteTaskService.py").is_file()
    assert (base / "__init__.py").is_file()  # _ensure_pkg


def test_make_seeder_writes_to_app_dir(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_dir", str(tmp_path / "app"))

    make_mod.make_seeder("Tasks", "Task")

    base = tmp_path / "app" / "Modules" / "Tasks" / "Seeders"
    assert (base / "TaskSeeder.py").is_file()
    assert (base / "__init__.py").is_file()  # _ensure_pkg


def test_make_factory_writes_to_app_dir(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_dir", str(tmp_path / "app"))

    make_mod.make_factory("Tasks", "Task")

    base = tmp_path / "app" / "Modules" / "Tasks" / "Factories"
    assert (base / "TaskFactory.py").is_file()
    assert (base / "__init__.py").is_file()  # _ensure_pkg


def test_make_serializer_writes_to_app_dir(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_dir", str(tmp_path / "app"))

    make_mod.make_serializer("Tasks", "Task")

    base = tmp_path / "app" / "Modules" / "Tasks" / "Serializers"
    assert (base / "TaskSerializer.py").is_file()
    assert (base / "__init__.py").is_file()  # _ensure_pkg
