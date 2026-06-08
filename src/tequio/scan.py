"""tequio scan — análisis automático y extensible de la app (estilo tequio).

Se engancha al auto-discovery (que YA recorre todos los módulos de la app) para construir un
AppModel: por cada módulo, sus imports de TERCEROS al top-level y su estado tras el discovery
(eager = cargado / lazy = diferido con tequio.lazy / absent = solo dentro de funciones). Luego
corre las CAPACIDADES — checks especializados por concern (lazy, http, db, mongo, ...) que el
core trae y que la app/plugins amplían soltando una clase `@capability` (mismo trato que
tasks/observers: el discovery las encuentra). Cada capacidad emite Findings.

    jornal scan              # todas las capacidades sobre tu app
    jornal scan --only http  # solo la de http

Diferencia con Django (que registra checks a mano): aquí el modelo lo construye el discovery
que YA existe, y las capacidades se auto-descubren. No es ad-hoc: opera sobre un modelo real
de la app (grafo de imports + estado runtime).
"""

from __future__ import annotations

import ast
import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ── Hallazgos ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Finding:
    """Un resultado de una capacidad sobre un módulo."""

    capability: str
    severity: str  # 'warn' | 'info' | 'ok'
    module: str
    message: str
    hint: str = ""


# ── Modelo de la app ──────────────────────────────────────────────────────────────
@dataclass
class ModuleInfo:
    dotted: str
    path: Path
    top_imports: list[str] = field(default_factory=list)  # terceros importados EAGER al top-level
    lazy_imports: list[str] = field(default_factory=list)  # libs vía `from tequio.lazy import X` (✓)


@dataclass
class AppModel:
    modules: list[ModuleInfo]
    state: dict[str, str]  # {paquete_top: 'eager'|'lazy'|'absent'} tras el discovery

    def importers_of(self, pkg: str) -> list[ModuleInfo]:
        return [m for m in self.modules if pkg in m.top_imports]


_STDLIB = set(sys.stdlib_module_names)
_OWN = {"milpa", "tequio", "app"}


def _is_third_party(top: str) -> bool:
    return bool(top) and top not in _STDLIB and top not in _OWN and not top.startswith("_")


_LAZY_MODULES = {"milpa.lazy", "tequio.lazy"}


def _top_level_imports(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Devuelve (eager, lazied) del CUERPO del módulo (no dentro de funciones ni TYPE_CHECKING):
    - eager  = terceros importados directo al top-level (los que el discovery carga y pesan).
    - lazied = libs traídas vía `from tequio.lazy import X` (el patrón bueno — diferidas)."""
    eager: set[str] = set()
    lazied: set[str] = set()
    for node in tree.body:  # solo top-level
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if _is_third_party(top):
                    eager.add(top)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module in _LAZY_MODULES:  # from tequio.lazy import openpyxl, pandas
                lazied.update(a.name.split(".")[0] for a in node.names)
            else:
                top = node.module.split(".")[0]
                if _is_third_party(top):
                    eager.add(top)
    return eager, lazied


def _state(lib: str) -> str:
    mod = sys.modules.get(lib)
    if mod is None:
        return "absent"
    return "lazy" if type(mod).__name__ == "_LazyModule" else "eager"


def build_model(modules_package: str) -> AppModel:
    """Descubre (importa) los módulos de la app, parsea sus imports al top-level, y lee el
    estado eager/lazy de cada lib tras el discovery — reproduciendo lo que carga un proceso."""
    pkg = importlib.import_module(modules_package)
    base = Path(pkg.__file__).parent  # type: ignore[arg-type]
    modules: list[ModuleInfo] = []
    all_libs: set[str] = set()
    for path in sorted(base.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        rel = path.relative_to(base).with_suffix("")
        dotted = f"{modules_package}." + ".".join(rel.parts)
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError, UnicodeDecodeError:
            continue
        eager, lazied = _top_level_imports(tree)
        if eager or lazied:
            modules.append(
                ModuleInfo(
                    dotted=dotted,
                    path=path,
                    top_imports=sorted(eager),
                    lazy_imports=sorted(lazied),
                )
            )
            all_libs.update(eager)
        # importar el módulo = lo que hace el discovery real (carga lo que cargue al top-level)
        try:
            importlib.import_module(dotted)
        except Exception:  # noqa: BLE001 — un módulo que no importa no debe tumbar el scan
            pass
    return AppModel(modules=modules, state={lib: _state(lib) for lib in sorted(all_libs)})


# ── Capacidades (el core trae las suyas; la app suelta `@capability` y se descubre) ─────
_CAPABILITIES: list[Capability] = []


class Capability:
    name = "?"

    def analyze(self, model: AppModel) -> list[Finding]:
        raise NotImplementedError


def capability(cls: type[Capability]) -> type[Capability]:
    """Registra una capacidad. El discovery de la app importa los módulos donde vivan las
    capacidades propias, así que registrarse al importar basta (estilo tequio)."""
    _CAPABILITIES.append(cls())
    return cls


_HEAVY = {
    "openpyxl",
    "pandas",
    "numpy",
    "scipy",
    "torch",
    "tensorflow",
    "reportlab",
    "PIL",
    "matplotlib",
    "faker",
    "lxml",
    "cv2",
    "sklearn",
    "transformers",
    "polars",
}


@capability
class _Lazy(Capability):
    """Libs pesadas importadas eager por el discovery — cargadas en procesos que quizá no las usan."""

    name = "lazy"

    def analyze(self, model: AppModel) -> list[Finding]:
        out: list[Finding] = []
        for m in model.modules:
            for lib in m.top_imports:  # importadas EAGER (el problema)
                if lib in _HEAVY:
                    out.append(
                        Finding(
                            "lazy",
                            "warn",
                            m.dotted,
                            f"'{lib}' se importa EAGER al top-level — el auto-discovery la carga en "
                            "TODO proceso (el worker que no la usa, el cron efímero, etc.).",
                            hint=f"Si este proceso no siempre la usa: `from tequio.lazy import {lib}`.",
                        )
                    )
            for lib in m.lazy_imports:  # ya vía tequio.lazy (el patrón bueno)
                if lib in _HEAVY:
                    out.append(
                        Finding(
                            "lazy",
                            "ok",
                            m.dotted,
                            f"'{lib}' ya está diferida con tequio.lazy ✓ — no pesa donde no se usa.",
                        )
                    )
        return out


_HTTP = {"requests", "httpx", "aiohttp", "urllib3"}


@capability
class _Http(Capability):
    """Clientes http crudos: candidatos a centralizar (timeouts/observabilidad) y a diferir."""

    name = "http"

    def analyze(self, model: AppModel) -> list[Finding]:
        out: list[Finding] = []
        for m in model.modules:
            for lib in m.top_imports:
                if lib in _HTTP:
                    eager = model.state.get(lib) == "eager"
                    extra = " (además EAGER: difiérelo con tequio.lazy si no se usa siempre)" if eager else ""
                    out.append(
                        Finding(
                            "http",
                            "info",
                            m.dotted,
                            f"Cliente http crudo ('{lib}'){extra}.",
                            hint="Centraliza timeouts/reintentos/trazas en un cliente compartido.",
                        )
                    )
        return out


@capability
class _Db(Capability):
    """Engine/session de SQLAlchemy armados a mano — saltan la sesión ambiente de tequio."""

    name = "db"
    _RAW = {"create_engine", "sessionmaker", "scoped_session"}

    def analyze(self, model: AppModel) -> list[Finding]:
        out: list[Finding] = []
        for m in model.modules:
            try:
                tree = ast.parse(m.path.read_text())
            except SyntaxError, UnicodeDecodeError:
                continue
            used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} & self._RAW
            if used:
                out.append(
                    Finding(
                        "db",
                        "warn",
                        m.dotted,
                        f"Arma SQLAlchemy a mano ({', '.join(sorted(used))}).",
                        hint="Usa la sesión ambiente de tequio (tequio.Core.Database / @transactional).",
                    )
                )
        return out


@capability
class _Mongo(Capability):
    """Driver de Mongo crudo — candidato a provider lazy (config por .env)."""

    name = "mongo"

    def analyze(self, model: AppModel) -> list[Finding]:
        out: list[Finding] = []
        for m in model.modules:
            for lib in m.top_imports:
                if lib in {"pymongo", "motor"}:
                    out.append(
                        Finding(
                            "mongo",
                            "info",
                            m.dotted,
                            f"Driver de Mongo crudo ('{lib}').",
                            hint="Aísla la conexión: lazy + config por .env (patrón provider estilo tequio).",
                        )
                    )
        return out


@capability
class _Auth(Capability):
    """Seguridad de la auth WEB: CSP (mitiga el robo de token por XSS cuando la auth usa un
    cookie legible por JS), CSRF. Solo aplica a apps con capa web — un worker-only no expone esto."""

    name = "auth"

    def analyze(self, model: AppModel) -> list[Finding]:
        from tequio.Core.Config import settings

        out: list[Finding] = []
        # Sin capa web (worker-only) no hay settings de CSP/CSRF: nada que revisar.
        if not hasattr(settings, "content_security_policy"):
            return out
        where = "config (.env)"
        if not getattr(settings, "content_security_policy", ""):
            out.append(
                Finding(
                    "auth",
                    "warn",
                    where,
                    "Sin CSP: si la auth usa un cookie legible por JS (Bearer leído desde cookie), "
                    "un XSS puede robar el token. CSP es la mitigación que NO toca el flujo de auth.",
                    hint="tequio trae CSP report-only por default; defínelo (no lo vacíes).",
                )
            )
        elif getattr(settings, "csp_report_only", True):
            out.append(
                Finding(
                    "auth",
                    "info",
                    where,
                    "CSP en Report-Only: observa las violaciones pero NO bloquea (seguro, pero aún "
                    "no protege de verdad).",
                    hint="Afina con los reportes y pon csp_report_only=false (enforcing) cuando esté limpio.",
                )
            )
        if not getattr(settings, "csrf_enabled", True):
            out.append(
                Finding(
                    "auth",
                    "info",
                    where,
                    "CSRF deshabilitado.",
                    hint="Si usas el carril cookie/sesión (no solo Bearer), considera habilitarlo.",
                )
            )
        return out


# ── Runner + reporte ────────────────────────────────────────────────────────────────
def scan(modules_package: str, only: str | None = None) -> list[Finding]:
    """Construye el modelo y corre las capacidades (todas, o solo `only`)."""
    model = build_model(modules_package)
    caps = [c for c in _CAPABILITIES if only is None or c.name == only]
    findings: list[Finding] = []
    for cap in caps:
        findings.extend(cap.analyze(model))
    return findings


def capability_names() -> list[str]:
    return sorted(c.name for c in _CAPABILITIES)


def format_report(findings: list[Finding]) -> str:
    """Reporte legible, agrupado por severidad."""
    icon = {"warn": "⚠", "info": "•", "ok": "✓"}
    order = {"warn": 0, "info": 1, "ok": 2}
    lines: list[str] = []
    for f in sorted(findings, key=lambda x: (order.get(x.severity, 9), x.capability, x.module)):
        short = f.module.replace("app.Modules.", "…")
        lines.append(f"  {icon.get(f.severity, '·')} [{f.capability}] {short}")
        lines.append(f"      {f.message}")
        if f.hint:
            lines.append(f"      → {f.hint}")
    warn = sum(1 for f in findings if f.severity == "warn")
    info = sum(1 for f in findings if f.severity == "info")
    ok = sum(1 for f in findings if f.severity == "ok")
    lines.append(f"\n  Resumen: {warn} a revisar · {info} sugerencias · {ok} ya en estilo tequio")
    return "\n".join(lines) if findings else "  Nada que reportar (o ninguna capacidad aplica)."
