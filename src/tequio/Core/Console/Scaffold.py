"""Scaffolder de proyectos: la lógica detrás de `tequio new <app>`.

Copia el skeleton EMBEBIDO (tequio/_skeleton, archivos `.tmpl`) y lo renderiza
(sustituye `__PROJECT__` por el nombre del proyecto, quita el sufijo `.tmpl`) para crear
un proyecto listo para correr. El skeleton se localiza con `importlib.resources`
(funciona instalado vía pip o en el repo), NUNCA con aritmética de `__file__`.
"""

from __future__ import annotations

from importlib.resources import as_file, files
from pathlib import Path

_PLACEHOLDER = "__PROJECT__"
_TMPL_SUFFIX = ".tmpl"

# Con `--demo`: módulo de demostración y modelos que el framework trae y que se MATERIALIZAN como
# código de usuario (single source of truth: viven una sola vez en el paquete tequio).
_DEMO_MODULES = ("Modules/Demo",)
_DEMO_MODELS = ("Models/Note.py",)
# Migración del demo que tequio COPIA al proyecto (divergencia vs milpa, que la autogenera):
# vive en el RAÍZ del proyecto (migrations/versions/), no en app/. Es una migración SOLO-notes
# (sin tabla users: Auth está excluido de tequio). El path debe coincidir con el que deja el
# analista de DB/migraciones en tequio/migrations/versions/.
_DEMO_MIGRATIONS = ("migrations/versions/b1f4notes01_notes.py",)
# Reescritura de imports al copiar: del paquete framework al código del proyecto.
_IMPORT_REWRITES = (("tequio.Modules.", "app.Modules."), ("tequio.Models.", "app.Models."))


def new_project(name: str, *, parent: Path | None = None, demo: bool = False) -> Path:
    """Crea el proyecto `name` desde el skeleton embebido. Devuelve la ruta creada.

    Seguro/idempotente: si el destino ya existe y NO está vacío, lanza `FileExistsError`
    (nunca sobrescribe trabajo del usuario). Deja también un `.env` listo (copia del
    `.env.example` generado) para que el proyecto arranque sin pasos extra.

    Con `demo=True` además copia el módulo Demo del framework (notas + eventos/observers +
    mediator/pipeline + jobs/crons + factories/seeders) + el modelo Note + la migración notes
    al `app/` del proyecto (y la migración al RAÍZ), reescribiendo sus imports internos — un
    starter kit + referencia viva de cómo funciona todo.
    """
    dest = (parent or Path.cwd()) / name
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(f"El destino '{dest}' ya existe y no está vacío.")

    source = files("tequio").joinpath("_skeleton")
    with as_file(source) as skeleton_dir:
        _render_tree(Path(skeleton_dir), dest, name)

    env_example = dest / ".env.example"
    env_file = dest / ".env"
    if env_example.is_file() and not env_file.exists():
        env_file.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")

    if demo:
        _add_demo(dest)
    return dest


def _add_demo(dest: Path) -> None:
    """Materializa el módulo Demo del paquete tequio (jobs/crons + eventos/observers +
    mediator/pipeline + factories/seeders) en `dest/app` y su migración notes,
    reescribiendo imports del framework (`tequio.Modules`/`tequio.Models`) a los del
    proyecto (`app.*`)."""
    package = files("tequio")
    with as_file(package) as package_dir:
        package_root = Path(package_dir)
        for relative in (*_DEMO_MODULES, *_DEMO_MODELS):
            _copy_rewritten(package_root / relative, dest / "app" / relative)
        # Las migraciones viven en migrations/versions/ del RAÍZ del proyecto, NO en app/:
        # loop SEPARADO que copia a dest/<relative> (no a dest/app/<relative>).
        for relative in _DEMO_MIGRATIONS:
            _copy_rewritten(package_root / relative, dest / relative)


def _copy_rewritten(src: Path, out: Path) -> None:
    """Copia `src` → `out` (archivo o árbol). En archivos .py reescribe los imports del
    framework a los del proyecto; el resto (.yml, .css, binarios) se copia tal cual."""
    files_to_copy = [src] if src.is_file() else sorted(src.rglob("*"))
    for source_file in files_to_copy:
        if source_file.is_dir() or "__pycache__" in source_file.parts:
            continue
        out_path = out if src.is_file() else out / source_file.relative_to(src)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if source_file.suffix == ".py":
            content = source_file.read_text(encoding="utf-8")
            for old, new in _IMPORT_REWRITES:
                content = content.replace(old, new)
            out_path.write_text(content, encoding="utf-8")
        else:
            out_path.write_bytes(source_file.read_bytes())


def _render_tree(skeleton_dir: Path, dest: Path, name: str) -> None:
    """Copia recursivamente el skeleton a `dest`. Regla por sufijo: los `.tmpl` son
    PLANTILLAS de texto (se sustituye el placeholder por `name` y se quita el sufijo);
    todo lo demás se copia BYTE a byte tal cual — así el skeleton puede traer binarios
    (cualquier binario que traiga el skeleton) sin que un read_text los corrompa."""
    # rglob sobre una ruta inexistente produce CERO items sin error: un skeleton
    # ausente (wheel mal empaquetado) sería un no-op silencioso. Nunca falla en silencio.
    if not skeleton_dir.is_dir():
        raise FileNotFoundError(f"Skeleton no encontrado en el paquete tequio: '{skeleton_dir}'.")
    for src in sorted(skeleton_dir.rglob("*")):
        if src.is_dir() or "__pycache__" in src.parts:
            continue
        rel = src.relative_to(skeleton_dir)
        out_path = dest / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if rel.name.endswith(_TMPL_SUFFIX):
            out_path = dest / rel.parent / rel.name[: -len(_TMPL_SUFFIX)]
            content = src.read_text(encoding="utf-8").replace(_PLACEHOLDER, name)
            out_path.write_text(content, encoding="utf-8")
        else:
            out_path.write_bytes(src.read_bytes())
