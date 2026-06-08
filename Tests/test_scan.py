"""Tests de tequio.scan: parseo del modelo + capacidades (lógica pura, sin discovery real)."""

from __future__ import annotations

import ast
from pathlib import Path

from tequio import scan as scan_mod
from tequio.scan import AppModel, Finding, ModuleInfo, _Db, _Http, _Lazy, capability_names


def test_top_level_imports_separates_eager_lazy_and_ignores_nested() -> None:
    code = (
        "from __future__ import annotations\n"
        "import openpyxl\n"
        "from pandas import DataFrame\n"
        "from tequio.lazy import numpy\n"
        "def f():\n"
        "    import scipy\n"  # dentro de función -> NO es top-level
    )
    eager, lazied = scan_mod._top_level_imports(ast.parse(code))
    assert "openpyxl" in eager
    assert "pandas" in eager  # 'from pandas import X' cuenta el paquete top
    assert "numpy" in lazied  # 'from tequio.lazy import X' -> es el patrón bueno
    assert "scipy" not in eager and "scipy" not in lazied  # nested no cuenta


def test_third_party_filter_excludes_stdlib_and_own() -> None:
    code = "import os\nimport tequio\nimport app\nimport openpyxl\n"
    eager, _ = scan_mod._top_level_imports(ast.parse(code))
    assert eager == {"openpyxl"}  # os (stdlib), tequio/app (propios) NO cuentan


def _model(top: list[str], lazy: list[str], state: dict[str, str]) -> AppModel:
    return AppModel(
        modules=[ModuleInfo("app.Modules.X", Path("/x.py"), top_imports=top, lazy_imports=lazy)],
        state=state,
    )


def test_lazy_capability_warns_on_eager_heavy() -> None:
    findings = _Lazy().analyze(_model(["openpyxl"], [], {"openpyxl": "eager"}))
    assert any(f.severity == "warn" and "openpyxl" in f.message for f in findings)


def test_lazy_capability_credits_tequio_lazy_usage() -> None:
    findings = _Lazy().analyze(_model([], ["openpyxl"], {}))
    assert any(f.severity == "ok" for f in findings)


def test_lazy_capability_ignores_non_heavy() -> None:
    findings = _Lazy().analyze(_model(["click"], [], {"click": "eager"}))  # click no es "pesada"
    assert findings == []


def test_http_capability_flags_raw_client() -> None:
    findings = _Http().analyze(_model(["httpx"], [], {"httpx": "eager"}))
    assert any(f.capability == "http" and "httpx" in f.message for f in findings)


def test_db_capability_flags_raw_engine(tmp_path: Path) -> None:
    f = tmp_path / "m.py"
    f.write_text("from sqlalchemy import create_engine\ne = create_engine('sqlite://')\n")
    model = AppModel(modules=[ModuleInfo("app.Modules.M", f, [], [])], state={})
    findings = _Db().analyze(model)
    assert any(f.capability == "db" for f in findings)


def test_builtin_capabilities_are_registered() -> None:
    assert set(capability_names()) >= {"lazy", "http", "db", "mongo"}


def test_format_report_handles_empty() -> None:
    assert "Nada que reportar" in scan_mod.format_report([])
    out = scan_mod.format_report([Finding("lazy", "warn", "app.X", "msg", "hint")])
    assert "[lazy]" in out and "hint" in out


def test_auth_capability(monkeypatch: object) -> None:
    """auth: en app web flagea CSP report-only / sin CSP; en worker-only (sin esos settings)
    se salta sin tronar. El mismo código kernel funciona en milpa y tequio."""
    from tequio.Core.Config import settings
    from tequio.scan import _Auth

    empty = AppModel(modules=[], state={})
    if not hasattr(settings, "content_security_policy"):
        assert _Auth().analyze(empty) == []  # worker-only: nada que revisar
        return
    monkeypatch.setattr(settings, "content_security_policy", "default-src 'self'")  # type: ignore[attr-defined]
    monkeypatch.setattr(settings, "csp_report_only", True)  # type: ignore[attr-defined]
    assert any("Report-Only" in f.message for f in _Auth().analyze(empty))
    monkeypatch.setattr(settings, "content_security_policy", "")  # type: ignore[attr-defined]
    assert any(f.severity == "warn" for f in _Auth().analyze(empty))
