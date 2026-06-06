"""Decorador `console_command` + discovery de commands de CLI (≈ artisan).

Re-exporta la API pública para que los consumers importen con
`from tequio.Core.Console import console_command` (mismo patrón que `Core/Cron`).
"""

from __future__ import annotations

from tequio.Core.Console.Console import (
    RegisteredCommand,
    build_cli_apps,
    build_command_table,
    console_command,
    format_command_list,
    import_submodules,
    registered_commands,
    reset_registry,
)

__all__ = [
    "RegisteredCommand",
    "build_cli_apps",
    "build_command_table",
    "console_command",
    "format_command_list",
    "import_submodules",
    "registered_commands",
    "reset_registry",
]
