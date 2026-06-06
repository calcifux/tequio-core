"""Kernel de consola — arma la app de Typer (≈ app/Console/Kernel.php de Laravel).

NO es el entrypoint: ese es el script `tequio` (definido en pyproject como
`tequio = tequio.Core.Console.Cli:run`), que solo hace `run()`. Aquí vive la
lógica: descubre los commands (Core + generales + módulos) y los monta como
sub-apps de Typer. No declara commands hardcodeados; se auto-descubren
(`@console_command` + discovery), así que agregar uno nuevo es solo crear su
archivo — este módulo no se vuelve a editar.

Uso (vía el script `tequio`):
    tequio list                  # ve todos los comandos
    tequio queue work            # arranca el worker de Celery

Vive en CORE (framework): NO importa Modules de forma estática — el discovery es
DINÁMICO (`import_submodules` + `iter_cli_apps`), igual que el kernel web. Por eso
puede vivir en Core sin romper "Core ↛ Modules" (que es sobre imports estáticos).
"""

from __future__ import annotations

import typer
from loguru import logger
from rich.console import Console

from tequio.Core.Config import settings
from tequio.Core.Console import build_command_table, import_submodules
from tequio.Core.Errors import DomainError
from tequio.Core.Logging import setup_logging
from tequio.Core.Registry import iter_cli_apps

# pretty_exceptions_enable=False: NOSOTROS controlamos el render de errores (ver `run`), para no
# escupir el traceback crudo de Typer/Rich (con locals) ante un error esperado de dominio.
app = typer.Typer(
    help=f"{settings.app_name} — comandos de consola (tequio 🤝).",
    pretty_exceptions_enable=False,
)


@app.callback()
def main() -> None:
    """Sin esto, Typer colapsa la app de un solo comando y no exige el nombre
    del subcomando. El callback la fuerza a modo "grupo" (estilo artisan), para
    que se invoque siempre como `<grupo> <command>` y soporte más comandos después.
    """


@app.command(name="list", help="Lista todos los comandos disponibles. (≈ php artisan list)")
def list_commands() -> None:
    """El `--help` de la raíz solo muestra los grupos; esto lista TODO (comandos raíz como
    `list` + cada `<grupo> <command>`) con su ayuda, en tabla rich coloreada."""
    general = sorted((command.name or "", command.help or "") for command in app.registered_commands if command.name)
    Console().print(build_command_table(general))


@app.command(name="new", help="Crea un proyecto nuevo de tequio desde una plantilla. (≈ laravel new).")
def new(
    name: str = typer.Argument(..., help="Nombre del proyecto (carpeta a crear en el dir actual)."),
    demo: bool = typer.Option(
        False,
        "--demo",
        "--full-demo",
        help="Incluye el módulo Demo de ejemplo (notas + eventos/observers + mediator/pipeline + "
        "jobs/crons + factories/seeders): starter kit y referencia viva.",
    ),
) -> None:
    """Genera un proyecto LISTO para correr: app/ (con un módulo Hello de ejemplo), jornal,
    .env y migrations/, con la config apuntando a TU código (MODULES_PACKAGE=app.Modules…).

    Con `--demo` copia además el módulo Demo (el sistema completo de referencia)."""
    from tequio.Core.Console.Scaffold import new_project

    console = Console()
    try:
        dest = new_project(name, demo=demo)
    except FileExistsError as error:
        console.print(f"[red]✗[/red] {error}")
        raise typer.Exit(code=1) from error
    console.print(f"[green]✓[/green] Proyecto creado en [bold]{dest}[/bold] 🤝\n")
    console.print("Siguientes pasos:")
    console.print(f"  [cyan]cd {name}[/cyan]")
    console.print("  [cyan]uv sync[/cyan]                 # instala tequio + dependencias")
    if demo:
        # OJO: con --demo NO va `migrate make`: la migración de notes ya viene COPIADA en el
        # proyecto (autogenerate fallaría con "Target database is not up to date").
        console.print("  [cyan]python jornal migrate run[/cyan]   # aplica la migración que ya trae el demo")
        console.print("  [cyan]python jornal db seed[/cyan]   # puebla notas (DemoSeeder)")
        console.print("  [cyan]python jornal queue work[/cyan]   # arranca el worker (procesa los @job)")
    else:
        console.print("  [cyan]python jornal list[/cyan]       # ve los comandos disponibles")


# Dispara los decoradores de los commands del FRAMEWORK (Core) —p. ej. `queue
# work` y `schedule work`— y de los commands GENERALES del proyecto (app-level).
# El discovery importa cada archivo y, al importarse, sus `@console_command` se
# registran. Debe ir ANTES del loop para que ya estén en el registro cuando
# `iter_cli_apps` arme los grupos.
import_submodules("tequio.Core.Console.Commands")
import_submodules(settings.app_commands_package)

# Monta cada grupo descubierto (módulos activos + generales) como sub-app de
# Typer. Así el CLI no necesita saber qué commands existen: solo los enchufa.
for group, sub_app in iter_cli_apps():
    app.add_typer(sub_app, name=group)


def _render_cli_error(error: BaseException) -> int:
    """Renderiza un error del CLI y devuelve el exit code. Simétrico al handler HTTP RFC 9457:
    un `DomainError` (esperado) sale como mensaje LIMPIO + su código, SIN traceback; uno inesperado
    (bug) sale conciso en stdout, y su traceback COMPLETO al log vía loguru (observable a las 3am;
    con valores solo en dev, ver setup_logging). Nada se traga: todo error deja rastro."""
    console = Console()
    if isinstance(error, DomainError):
        console.print(f"[red]✗[/red] {error.message} [dim]({error.error_code})[/dim]")
        return 1
    logger.opt(exception=True).error("CLI | error inesperado ({t})", t=type(error).__name__)
    console.print(f"[red]✗[/red] Error interno ({type(error).__name__}). El detalle quedó en el log.")
    return 1


def run() -> None:
    """Entrypoint del CLI (lo llama el script `tequio`). Envuelve `app()`
    con el borde de error: sin esto, cualquier error escupía el traceback crudo de Typer en consola."""
    setup_logging()  # sinks configurados (stderr concisa sin fuga de valores en prod + archivo)
    try:
        app()
    except DomainError as error:
        raise SystemExit(_render_cli_error(error)) from None
    except Exception as error:  # noqa: BLE001 — borde final del CLI: nada escapa sin loguearse
        raise SystemExit(_render_cli_error(error)) from None


if __name__ == "__main__":
    run()
