"""Catálogo de Códigos de Contenido.

En ADS un mensaje no dice A QUIÉN va, sino QUÉ es. Cada célula mira el código
y decide si le interesa. Este catálogo lo usan las células; el nodo NO lo
importa, porque solo inunda sin interpretar el contenido.

Los códigos REQ y RES son los del enunciado (§7). ACK viene del modelo de
acuses visto en clase y SRV_LAT de los latidos de disponibilidad.
"""

SERVICIOS = ("SUM", "SUB", "MUL", "DIV")

NOMBRES = {"SUM": "Suma", "SUB": "Resta", "MUL": "Multiplicación", "DIV": "División"}
SIMBOLOS = {"SUM": "+", "SUB": "−", "MUL": "×", "DIV": "÷"}

REQ = "REQ"
ACK = "ACK"
RES = "RES"
TIPOS = (REQ, ACK, RES)

SRV_LAT = "SRV_LAT"            # latido de un servidor
SONDA_PRUEBA = "SONDA_PRUEBA"  # solo lo inyecta la sonda; ninguna célula lo procesa


def codigo(servicio: str, tipo: str) -> str:
    """codigo("SUM", REQ) -> "SUM_REQ"."""
    return f"{servicio}_{tipo}"


def separar(cod) -> tuple[str, str] | None:
    """"SUM_REQ" -> ("SUM", "REQ"). None si no es un código de operación."""
    if not isinstance(cod, str):
        return None
    servicio, _, tipo = cod.partition("_")
    if servicio in SERVICIOS and tipo in TIPOS:
        return servicio, tipo
    return None


CATALOGO = {codigo(s, t): (s, t) for s in SERVICIOS for t in TIPOS}
CATALOGO[SRV_LAT] = (None, "LAT")
CATALOGO[SONDA_PRUEBA] = (None, "PRUEBA")
