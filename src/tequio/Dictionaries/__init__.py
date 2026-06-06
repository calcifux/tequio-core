"""Dictionaries compartidos: constantes centralizadas (DRY), equivalente a los
`const` Dictionary del legacy. Un solo lugar para los valores repetidos.

Auto-discovery: cada diccionario vive en su propio submódulo y se importa directo
(`from tequio.Dictionaries.MiDictionary import MiDictionary`). Sueltas un archivo
nuevo y funciona, sin tocar este `__init__` ni mantener una lista de re-exports.

A diferencia de `app/Models` (que SÍ corre pkgutil para que SQLAlchemy registre todos
los modelos y resuelva las relaciones por string), los diccionarios son clases de
constantes: no hay nada que registrar, así que este paquete no necesita escanear nada.
"""
