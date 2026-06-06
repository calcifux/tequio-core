"""Auto-registro de commands de CLI con discovery por convención (≈ artisan).

`@console_command` marca una función como command de Typer y la auto-registra
en su GRUPO, igual que `@cron_task` registra una task de Celery. El grupo se
deduce del módulo (`app.Modules.<X>...` → `"<x>"`); los commands GENERALES
(`app.Console.Commands.*`) deben declarar `group=` explícito.

El command es un ADAPTER DELGADO y MODE-AGNOSTIC: corre síncrono en el proceso
del CLI. El modo async NO es propiedad del command — se expresa despachando un
Job explícitamente (`Job.dispatch()` / `.dispatch_sync()`).

`build_cli_apps()` arma un `typer.Typer()` por grupo desde el registro;
`import_submodules()` es el discovery (pkgutil) que importa los archivos para
que los decoradores corran. El Registry los orquesta para los módulos activos.
"""

from __future__ import annotations

import importlib
import io
import pkgutil
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from tequio.Core.Discovery import _module_absent


@dataclass(frozen=True)
class RegisteredCommand:
    """Un command marcado con @console_command, listo para montarse en su grupo."""

    group: str
    name: str
    func: Callable[..., Any]
    help: str | None
    typer_kwargs: dict[str, Any]


# Registro global: grupo -> commands. Se llena cuando se importan los archivos
# (los decoradores corren). Mismo patrón module-level que los sinks de Cron.
_REGISTRY: dict[str, list[RegisteredCommand]] = {}


def _group_from_module(module_path: str) -> str | None:
    """Deduce el grupo del módulo de la función:
    `app.Modules.Example.Console.Commands.X` → `example`. Si no hay segmento
    `Modules` (p. ej. commands generales en `app.Console.Commands`), devuelve
    None y el decorador exige `group=` explícito.
    """
    parts = module_path.split(".")
    if "Modules" in parts:
        index = parts.index("Modules")
        if index + 1 < len(parts):
            return parts[index + 1].lower()
    return None


def console_command(
    name: str,
    *,
    group: str | None = None,
    help: str | None = None,
    **typer_kwargs: Any,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Marca y auto-registra una función como command de CLI.

    - `group`: si es None, se deduce del módulo (`app.Modules.<X>` → `<x>`).
      Para commands GENERALES (`app/Console/Commands`) es OBLIGATORIO declararlo.
    - La función NO se envuelve: queda intacta y reusable (sync) por quien sea.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        resolved_group = group if group is not None else _group_from_module(func.__module__)
        if resolved_group is None:
            raise ValueError(
                f"console_command '{name}' en {func.__module__}: no se pudo deducir el grupo "
                f"del módulo; declara group= explícito (es un command general, fuera de app.Modules)."
            )
        command = RegisteredCommand(
            group=resolved_group, name=name, func=func, help=help, typer_kwargs=dict(typer_kwargs)
        )
        _REGISTRY.setdefault(resolved_group, []).append(command)
        return func

    return decorator


def _group_callback() -> None:
    """No-op para forzar modo 'grupo' en el sub-app (se invoca como
    `<grupo> <command>`). Mismo truco que el callback de la app raíz."""


def build_cli_apps() -> Iterator[tuple[str, typer.Typer]]:
    """Arma un `typer.Typer()` por grupo desde el registro y hace yield de
    `(grupo, sub_app)`, ordenado por nombre de grupo (determinista). Los archivos
    ya deben estar importados (el discovery los importó antes de llamar acá).
    """
    for group in sorted(_REGISTRY):
        sub_app = typer.Typer(help=f"Comandos de '{group}'.")
        sub_app.callback()(_group_callback)
        for command in _REGISTRY[group]:
            sub_app.command(name=command.name, help=command.help, **command.typer_kwargs)(command.func)
        yield group, sub_app


def import_submodules(package_name: str, *, recursive: bool = False) -> None:
    """Importa todos los submódulos (que no empiecen con `_`) de un paquete,
    para disparar sus decoradores (@console_command, @cron_task). Discovery por
    convención con `pkgutil` — el mismo mecanismo que usan Celery/Django/pytest.

    Con `recursive=True` DESCIENDE a los sub-paquetes (`info.ispkg` → recursión),
    de modo que importa TODO el árbol del paquete, no solo su primer nivel. Esto es
    lo que libera el encarpetado: el discovery ya no exige una carpeta fija
    (`Jobs/`, `Observers/`, ...) — importa el módulo entero y los decoradores corren
    vivan donde vivan los archivos. Los nombres con `_` se saltan en CUALQUIER nivel
    (archivos y sub-paquetes privados quedan fuera del barrido).

    Si la carpeta de convención no existe, no hace nada (ausencia esperada). PERO si un
    archivo del módulo tiene un import roto, se RE-LANZA (faro: nunca silenciamos un bug real,
    si no tu @console_command/@cron_task "no se registra" sin señal).
    """
    try:
        package = importlib.import_module(package_name)
    except ModuleNotFoundError as error:
        if _module_absent(error, package_name):
            return  # la carpeta de convención no existe: ausencia esperada
        raise  # import roto DENTRO del módulo del usuario: que truene
    if not hasattr(package, "__path__"):
        return
    for info in pkgutil.iter_modules(package.__path__):
        if info.name.startswith("_"):
            continue
        child = f"{package_name}.{info.name}"
        if recursive and info.ispkg:
            import_submodules(child, recursive=True)  # baja al sub-paquete (todo el árbol)
        else:
            importlib.import_module(child)


def build_command_table(general: Sequence[tuple[str, str]] = ()) -> Table:
    """Tabla rich con TODOS los commands. `general` son los comandos RAÍZ (`list`…),
    que no van por grupo; el resto se lista como `<grupo> <command>`, ordenado por grupo+nombre.
    La imprime `tequio list` con color en la terminal.

    El `--help` de Typer en la raíz solo muestra los grupos (queue, schedule, ...) y omite los
    subcomandos y los comandos raíz; esto los lista todos de un jalazo.
    """
    table = Table(title="🤝 Labores del tequio", title_justify="left", header_style="bold")
    table.add_column("Comando", style="cyan", no_wrap=True)
    table.add_column("Descripción")
    for name, help_text in general:
        table.add_row(name, help_text)
    for group in sorted(_REGISTRY):
        for command in sorted(_REGISTRY[group], key=lambda registered: registered.name):
            table.add_row(f"{group} {command.name}", command.help or "")
    return table


def format_command_list() -> str:
    """Render del listado a STRING SIN color (para salida no-TTY, pipes y tests).

    `jornal list` imprime la tabla directo a una consola rich (coloreada en terminal);
    esta versión a string es el camino plano/determinista. Comparte `build_command_table`.
    """
    buffer = io.StringIO()
    Console(file=buffer, width=100, no_color=True).print(build_command_table())
    return buffer.getvalue()


def registered_commands() -> dict[str, list[RegisteredCommand]]:
    """Vista del registro (para tests/introspección)."""
    return {group: list(commands) for group, commands in _REGISTRY.items()}


def reset_registry() -> None:
    """Limpia el registro. SOLO para tests (aislar casos entre sí)."""
    _REGISTRY.clear()
