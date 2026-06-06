"""Guardrail: `src/tequio/Core/` (el framework tequio) debe ser GENÉRICO — sin branding del
proyecto. Si alguien mete "aklara" (u otra marca) en Core —en código, templates o
catálogos— este test TRUENA. Mantiene Core reutilizable/extraíble; la marca va en la
capa del proyecto (app/Resources, app/Modules). import-linter ya cubre el lado de
imports (Core↛Modules); esto cubre el lado del CONTENIDO.

¿Agregas otra marca/dominio que no deba filtrarse a Core? Mételo en _FORBIDDEN.
"""

from __future__ import annotations

from pathlib import Path

_CORE_DIR = Path(__file__).resolve().parents[2] / "src" / "tequio" / "Core"
_PROJECT_ROOT = _CORE_DIR.parents[2]
# Marcas / términos del proyecto que NO deben aparecer en el framework.
_FORBIDDEN = ("aklara",)


def test_core_has_no_project_branding() -> None:
    offenders: list[str] = []
    for path in _CORE_DIR.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8").lower()
        except UnicodeDecodeError, OSError:
            continue  # binarios u otros: ignorar
        for term in _FORBIDDEN:
            if term in text:
                offenders.append(f"  {path.relative_to(_PROJECT_ROOT)} → contiene '{term}'")

    assert not offenders, (
        "Core debe ser GENÉRICO (sin branding del proyecto). Mueve esto a la capa del "
        "proyecto (app/Resources, app/Modules):\n" + "\n".join(offenders)
    )
