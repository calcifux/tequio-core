"""Registry del monolito modular: descubre y ensambla los módulos presentes en
app/Modules/ (escaneo del filesystem). Re-exporta la API pública para que los
entrypoints (`app/Core/CeleryApp/CeleryApp.py`) sigan importando con
`from tequio.Core.Registry import ...`.
"""

from __future__ import annotations

from tequio.Core.Registry.Registry import (
    collect_beat_schedule,
    import_all_handlers,
    import_all_models,
    import_all_observers,
    import_all_seeders,
    import_all_tasks,
    iter_cli_apps,
    module_packages,
)

__all__ = [
    "collect_beat_schedule",
    "import_all_handlers",
    "import_all_models",
    "import_all_observers",
    "import_all_seeders",
    "import_all_tasks",
    "iter_cli_apps",
    "module_packages",
]
