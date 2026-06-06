"""Commands del FRAMEWORK (built-in), disponibles en cualquier proyecto que use
este Core: arrancar el worker (`queue work`) y el scheduler (`schedule work`).

Se auto-descubren igual que cualquier command (`@console_command` + pkgutil); el
entrypoint `app/Core/Console/Cli.py` los carga con `import_submodules`. Cuando Core se extraiga
como paquete, estos commands viajan con él —los 7 proyectos los tienen gratis—.
"""
