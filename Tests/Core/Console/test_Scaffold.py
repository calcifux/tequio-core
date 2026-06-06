"""Tests del scaffolder `tequio new` (Core/Console/Scaffold.py) — sin BD, puro filesystem.

Cubren el contrato base (skeleton renderizado, placeholder sustituido, idempotencia) y el
`--demo`: materializa el módulo Demo worker-side en `app/` con sus imports del framework
reescritos (`tequio.Modules.` → `app.Modules.`).

En milpa este archivo probaba además el FRONTEND del demo (`_skeleton_demo`: surcos Vite + PWA)
y sus binarios PNG intactos. tequio es worker-side (sin Vite/surcos/PWA): ese skeleton no existe,
así que esos tests se eliminan.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tequio.Core.Console.Scaffold import new_project


def test_new_project_renderiza_skeleton_y_sustituye_nombre(tmp_path: Path) -> None:
    dest = new_project("granja", parent=tmp_path)

    assert dest == tmp_path / "granja"
    pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
    assert "granja" in pyproject
    assert "__PROJECT__" not in pyproject
    assert (dest / ".env").is_file()  # listo para arrancar sin pasos extra
    assert not list(dest.rglob("*.tmpl"))  # ningún .tmpl se fuga al proyecto


def test_new_project_no_sobrescribe_destino_con_contenido(tmp_path: Path) -> None:
    (tmp_path / "ocupado").mkdir()
    (tmp_path / "ocupado" / "algo.txt").write_text("mío", encoding="utf-8")

    with pytest.raises(FileExistsError):
        new_project("ocupado", parent=tmp_path)


def test_demo_materializa_backend_con_imports_reescritos(tmp_path: Path) -> None:
    """El --demo materializa el módulo Demo worker-side en app/Modules/Demo, reescribiendo los
    imports del framework (tequio.Modules.*) a los del proyecto (app.Modules.*).

    El Demo usa el layout estilo make:* (un archivo por clase, agrupado por rol): el servicio vive
    en `Services/NoteService.py`. El discovery es libre, así que el demo lo demuestra."""
    dest = new_project("granja", parent=tmp_path, demo=True)

    note_service = dest / "app" / "Modules" / "Demo" / "Services" / "NoteService.py"
    assert note_service.is_file()
    content = note_service.read_text(encoding="utf-8")
    assert "tequio.Modules." not in content  # reescrito
    assert "app.Modules." in content  # a los imports del proyecto
