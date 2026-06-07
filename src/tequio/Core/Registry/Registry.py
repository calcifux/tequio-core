"""Registro del monolito modular: descubre y ensambla los módulos presentes.

Layout estilo Laravel (PascalCase). Los módulos viven en `MODULES_PACKAGE`
(default del skeleton: `app.Modules`; aquí en el repo: `tequio.Modules`) y se
descubren SOLOS escaneando esa carpeta con pkgutil.

ENCARPETADO LIBRE (tequio se suelta del rígido). El discovery YA NO exige una
estructura fija dentro de cada módulo: importa TODO el árbol del módulo de forma
recursiva (`import_submodules(package, recursive=True)`), así los decoradores
(@job / @cron_task / @console_command / @handles / la subclase de Seeder u
Observer) corren vivan donde vivan sus archivos. Organiza tu app como quieras:
"ya como haga el programador su aplicación, nos vale".

tequio PROPONE (como sugerencia de LECTURA, no como obligación) un layout plano:
  - `Console/Commands/` para el automontaje de los commands de CLI
  - `Jobs.py` / `Crons.py` / `Observers.py` / `Handlers.py` / `Seeders.py`
    como nombres legibles para cada estilo del catálogo.
Pero como el discovery baja por TODO el árbol, cualquier otro encarpetado
(subcarpetas, archivos sueltos, etc.) funciona igual. Lo especial sigue siendo
`Console/Kernel.py`: la VÍA DECLARATIVA del beat_schedule, con PRECEDENCIA. Porque
ahora los `@cron_task` descubiertos TAMBIÉN alimentan el beat (se convierten a
crontab y se agendan solos), Kernel.py deja de ser la única fuente y pasa a ser la
declaración explícita que GANA si su nombre colisiona con un cron auto-derivado.

Tener un módulo presente NO dispara nada por sí mismo:
  - Registrar tasks (`import_all_tasks`) solo las vuelve ejecutables bajo demanda.
  - El único disparo AUTOMÁTICO es `celery beat` leyendo el beat_schedule; y aun
    así, cada cron solo se ejecuta donde su guard `@cron_task(environments=[...])`
    lo permite. La autoridad del auto-disparo vive en `@cron_task`, no aquí: entrar
    al beat_schedule solo AGENDA; los gates (environments, anti-overlap) corren al
    EJECUTAR dentro del wrapper de `@cron_task`.

Los MODELOS NO viven por módulo: son COMPARTIDOS en app/Models (una sola fuente
por tabla, porque todos los módulos comparten la BD legacy).
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterator
from types import ModuleType

import typer

from tequio.Core.Config import settings
from tequio.Core.Console import build_cli_apps, import_submodules
from tequio.Core.Discovery import _module_absent


def module_packages() -> list[str]:
    """TODOS los módulos presentes en app/Modules/ (escaneo del filesystem con
    pkgutil). No hay concepto de "activo/inactivo": un módulo existe si su
    carpeta existe, igual que Laravel descubre los packages instalados. El
    control de qué corre solo NO está aquí, sino en `@cron_task` (environments)
    + en si arrancas `celery beat`."""
    package = settings.modules_package
    try:
        modules_root = importlib.import_module(package)
    except ModuleNotFoundError:
        return []  # paquete de módulos no presente (p. ej. proyecto recién creado): cero módulos
    if not hasattr(modules_root, "__path__"):
        return []
    return [
        f"{package}.{info.name}"
        for info in pkgutil.iter_modules(modules_root.__path__)
        if info.ispkg and not info.name.startswith("_")
    ]


def _try_import(dotted_path: str) -> ModuleType | None:
    try:
        return importlib.import_module(dotted_path)
    except ModuleNotFoundError as error:
        # Faro: None solo si el módulo objetivo no existe (ausencia esperada); si el import
        # falla por un bug DENTRO del módulo del usuario, se re-lanza (nunca se traga en silencio).
        if _module_absent(error, dotted_path):
            return None
        raise


def import_all_models() -> None:
    """Registra TODAS las tablas en Base.metadata. Basta importar el paquete: su
    __init__ auto-importa todos los modelos (self-discovery con pkgutil), así agregar
    un modelo = crear su archivo; no hay lista manual en ningún __init__."""
    importlib.import_module(settings.models_package)


def _import_all_modules() -> None:
    """Corazón del discovery libre: importa TODO el árbol de cada módulo presente
    (`import_submodules(package, recursive=True)`). Idempotente — `sys.modules`
    cachea, así llamarlo varias veces no reimporta. Es lo que vuelve la estructura
    interna del módulo IRRELEVANTE para el registro: corra el decorador donde corra,
    su archivo se importa.

    Las cuatro `import_all_*` de abajo delegan TODAS aquí (hacen exactamente lo
    mismo). Es deliberado.
    """
    for package in module_packages():
        import_submodules(package, recursive=True)


def import_all_tasks() -> None:
    """Importa el árbol completo de cada módulo para que las tasks (@job / @cron_task /
    @celery_app.task) queden registradas (las vuelve ejecutables; NO las dispara).

    Por qué sigue existiendo (y no se fusionó con las otras tres): el nombre es
    DOCUMENTACIÓN en el call-site — `import_all_tasks()` en CeleryApp dice "estoy
    cargando tasks". Con el encarpetado libre ya no importa una carpeta concreta
    (`Jobs/`, `Crons/`), por eso las cuatro delegan en `_import_all_modules` (un
    solo barrido recursivo del árbol); las mantenemos separadas para conservar la
    claridad de cada call-site y dejar la puerta abierta a re-especializarlas en el
    futuro (p. ej. filtrar por convención) sin tocar a quien las llama.
    """
    _import_all_modules()


def import_all_seeders() -> None:
    """Importa el árbol completo de cada módulo para que las subclases de `Seeder`
    se registren (las descubre `db:seed`).

    Alias de claridad (ver `import_all_tasks`): las cuatro `import_all_*` hacen lo
    mismo —un barrido recursivo del árbol del módulo— pero cada nombre documenta su
    call-site (aquí: `db:seed` cargando seeders) y deja la opción futura de
    re-especializar el discovery sin cambiar al llamador.
    """
    _import_all_modules()


def import_all_observers() -> None:
    """Importa el árbol completo de cada módulo para que las subclases de `Observer`
    se registren (las dispara `Events.dispatch`).

    Alias de claridad (ver `import_all_tasks`): las cuatro `import_all_*` hacen lo
    mismo —un barrido recursivo del árbol del módulo— pero cada nombre documenta su
    call-site (aquí: el bootstrap de eventos cargando observers) y deja abierta la
    re-especialización futura sin cambiar al llamador.
    """
    _import_all_modules()


def import_all_handlers() -> None:
    """Importa el árbol completo de cada módulo para que los `@handles(Cmd)` se
    registren (los resuelve `Mediator.send`).

    Alias de claridad (ver `import_all_tasks`): las cuatro `import_all_*` hacen lo
    mismo —un barrido recursivo del árbol del módulo— pero cada nombre documenta su
    call-site (aquí: el Mediator cargando handlers) y deja abierta la
    re-especialización futura sin cambiar al llamador.
    """
    _import_all_modules()


def collect_beat_schedule() -> dict[str, object]:
    """Arma el beat_schedule que `celery beat` programa, fusionando DOS fuentes:

    1. Los `@cron_task(schedule=...)` descubiertos (`registered_crons()`): cada uno
       se vuelve una entrada del beat, con su expresión cron de 5 campos convertida
       a `crontab` (vía `to_crontab`). La clave del dict es el nombre del cron (=
       nombre de la task de Celery); si declara `queue`, se enruta con
       `options={"queue": ...}` (el equivalente beat del `apply_async(queue=...)`
       que hace `schedule run`).
    2. Los `beat_schedule` declarados en cada `Console/Kernel.py` (la vía
       DECLARATIVA). Se aplican AL FINAL, así un nombre declarado en Kernel.py
       PRECEDE (sobrescribe) al cron auto-derivado con el mismo nombre.

    Que un cron entre al schedule NO equivale a EJECUTARLO: el beat solo AGENDA.
    Los gates (`environments`, anti-overlap por lock de redis) siguen viviendo en
    `@cron_task` y corren AL EJECUTAR dentro de su wrapper, no aquí. Y nada de esto
    corre si no arrancas el proceso `beat`. El discovery (`import_all_tasks()`) debe
    haber corrido antes para que `registered_crons()` esté poblado (lo garantiza
    CeleryApp en `on_after_configure`).
    """
    # Import DIFERIDO (no a nivel de módulo): Cron importa CeleryApp y CeleryApp
    # importa este Registry, así que importar Cron arriba cerraría el ciclo. Igual
    # que el discovery, esto se resuelve cuando la función corre (Celery ya
    # configurado), con todo el árbol cargado. qualified_queue (Core/CeleryApp) va
    # diferido por la misma razón: CeleryApp importa este Registry.
    from tequio.Core.CeleryApp import qualified_queue
    from tequio.Core.Cron import registered_crons, to_crontab

    schedule: dict[str, object] = {}
    # (1) Auto-derivados de @cron_task. registered_crons() solo trae los que tienen
    # schedule (los sin cadencia ya quedan fuera, ver Cron.py).
    for rc in registered_crons():
        entry: dict[str, object] = {"task": rc.name, "schedule": to_crontab(rc.schedule)}
        if rc.queue is not None:
            # qualified_queue aplica el QUEUE_NAMESPACE (bus compartido) si hay; igual que el
            # apply_async(queue=...) de `schedule run`, pero para la vía beat.
            entry["options"] = {"queue": qualified_queue(rc.queue)}
        schedule[rc.name] = entry
    # (2) Kernel.py por módulo, AL FINAL: precedencia en colisión de nombre.
    for package in module_packages():
        kernel = _try_import(f"{package}.Console.Kernel")
        if kernel and hasattr(kernel, "beat_schedule"):
            schedule.update(kernel.beat_schedule)
    return schedule


def iter_cli_apps() -> Iterator[tuple[str, typer.Typer]]:
    """Itera los sub-apps de Typer (grupo, sub_app) de todos los módulos presentes.

    Primero dispara el discovery: para cada módulo importa TODO su árbol con
    `import_submodules(package, recursive=True)`, lo que ejecuta los decoradores
    @console_command vivan donde vivan (tequio PROPONE `Console/Commands/` para el
    automontaje, pero el barrido recursivo encuentra el command en cualquier
    carpeta). Después delega en `build_cli_apps()`, que arma un Typer por grupo
    desde el registro ya poblado.

    El acoplamiento hacia los módulos es por imports DINÁMICOS (rutas en string):
    Core no importa Modules de forma estática, así que import-linter no marca una
    violación Core↛Modules.
    """
    for package in module_packages():
        import_submodules(package, recursive=True)
    yield from build_cli_apps()
