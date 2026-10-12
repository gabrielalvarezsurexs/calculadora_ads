"""La lógica de negocio: las cuatro operaciones. Solo la importa el servidor.

Adaptado del primer parcial. Cambios:

* Un servicio por llamada (``SUM``, ``SUB``, ``MUL``, ``DIV``), como los Códigos
  de Contenido, en lugar de un símbolo.
* Control de tipos: los operandos llegan por la red y pueden ser cualquier cosa
  JSON. ``bool`` se rechaza aunque en Python sea un ``int``.
* Control de finitos: nunca se devuelve NaN ni Infinity (no son JSON estándar).
  Un overflow es un ``error``, no un resultado.

Es una función PURA y nunca lanza: un error de dominio (división entre cero) es
una respuesta válida del sistema, no una falla del servidor.
"""

import math

from comun import codigos


def _operando(valor, nombre: str) -> tuple[float | None, str | None]:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None, f"operando {nombre} no es un número: {valor!r}"[:120]
    try:
        x = float(valor)
    except OverflowError:
        return None, f"operando {nombre} fuera de rango"
    if not math.isfinite(x):
        return None, f"operando {nombre} no es finito"
    return x, None


def calcular(servicio: str, a, b) -> tuple[float | None, str | None]:
    """Devuelve (resultado, error). Exactamente uno de los dos es None."""
    if servicio not in codigos.SERVICIOS:
        return None, f"servicio no soportado: {servicio!r}"
    x, error = _operando(a, "a")
    if error:
        return None, error
    y, error = _operando(b, "b")
    if error:
        return None, error

    try:
        if servicio == "SUM":
            r = x + y
        elif servicio == "SUB":
            r = x - y
        elif servicio == "MUL":
            r = x * y
        else:  # DIV
            if y == 0:
                return None, "división entre cero"
            r = x / y
    except OverflowError:
        return None, "resultado fuera de rango"
    if not math.isfinite(r):
        return None, "resultado fuera de rango (no finito)"
    return r, None
