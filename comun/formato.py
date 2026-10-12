"""Presentación: cómo se escriben números y operaciones para un humano.

Adaptado del primer parcial. Cambios: los flotantes se muestran con 12 cifras
significativas (así 0.1 + 0.2 se ve como 0.3) y solo se muestran como entero
si caben sin notación científica.

Este módulo no decide nada: solo formatea.
"""

from comun import codigos


def numero(valor) -> str:
    """7.0 -> '7'; 0.30000000000000004 -> '0.3'; 1e20 -> '1e+20'."""
    if valor is None:
        return "?"
    if isinstance(valor, bool):
        return str(valor)
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        if valor.is_integer() and abs(valor) < 1e15:
            return str(int(valor))
        return format(valor, ".12g")
    return str(valor)


def operacion(a, servicio: str, b, resultado=None, error=None) -> str:
    """Texto de una operación para logs y ventanas: '7 ÷ 2 = 3.5'."""
    izquierda = f"{numero(a)} {codigos.SIMBOLOS.get(servicio, servicio)} {numero(b)}"
    if error:
        return f"{izquierda} → ERROR: {error}"
    if resultado is None:
        return izquierda
    return f"{izquierda} = {numero(resultado)}"


def milisegundos(segundos: float) -> str:
    return f"{segundos * 1000:.0f} ms"
