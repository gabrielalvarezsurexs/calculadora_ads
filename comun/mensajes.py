"""Formato de los mensajes: el sobre de datos y los mensajes de control.

Hay dos familias, y nunca se mezclan:

* **Control** (protocolo de conexión, §10.1): HOLA, BIENVENIDA, PARES y
  RECHAZO. Llevan ``"ctrl"`` en lugar de ``"codigo"``, viajan por UN enlace y
  nunca se retransmiten.
* **Datos** (protocolo de comunicación, §10.2): siempre broadcast. Llevan el
  sobre de abajo. El nodo solo usa ``id``, ``ttl`` y ``ruta``; el resto lo lee
  únicamente para mostrarlo, y el ``cuerpo`` no lo abre nunca.

Sobre::

    {"id": "<sha256>", "codigo": "SUM_REQ", "origen": "<hash célula>",
     "tipo_origen": "INTERFAZ", "nombre_origen": "GUI-1", "ts": 1760100000.1,
     "ttl": 8, "ruta": ["<hash nodo>", ...], "cuerpo": {...}}
"""

import re
import time

from comun import config, huella

VERSION = 1

# Tipos de entidad que se presentan ante un nodo.
NODO = "NODO"
INTERFAZ = "INTERFAZ"
SERVIDOR = "SERVIDOR"
SONDA = "SONDA"
ENTIDADES = (NODO, INTERFAZ, SERVIDOR, SONDA)

# Mensajes de control.
HOLA = "HOLA"
BIENVENIDA = "BIENVENIDA"
PARES = "PARES"
RECHAZO = "RECHAZO"

# Motivos de RECHAZO.
DUPLICADO = "duplicado"
AUTOCONEXION = "autoconexion"
MOTIVO_VERSION = "version"
INVALIDO = "invalido"

_HEX64 = re.compile(r"[0-9a-f]{64}")
_ENDPOINT = re.compile(r"[^\s:]+:\d{1,5}")


def es_hash(valor) -> bool:
    return isinstance(valor, str) and _HEX64.fullmatch(valor) is not None


# --- Endpoints "host:puerto" ------------------------------------------------

def endpoint(host: str, puerto: int) -> str:
    return f"{host}:{puerto}"


def separar_endpoint(ep: str) -> tuple[str, int]:
    """'127.0.0.1:5001' -> ('127.0.0.1', 5001). ValueError si no es válido."""
    if not isinstance(ep, str) or not _ENDPOINT.fullmatch(ep.strip()):
        raise ValueError(f"endpoint inválido: {ep!r} (se espera host:puerto)")
    host, puerto = ep.strip().rsplit(":", 1)
    puerto = int(puerto)
    if not 0 < puerto < 65536:
        raise ValueError(f"puerto fuera de rango: {puerto}")
    return host, puerto


def endpoints_validos(lista) -> list[str]:
    """Filtra una lista recibida por la red: solo endpoints bien formados."""
    if not isinstance(lista, list):
        return []
    validos = []
    for ep in lista:
        try:
            validos.append(endpoint(*separar_endpoint(ep)))
        except ValueError:
            pass
    return validos


# --- Datos ------------------------------------------------------------------

def nuevo(codigo: str, origen: str, tipo_origen: str, nombre_origen: str,
          cuerpo: dict, ttl: int | None = None) -> dict:
    """Sobre de datos recién creado, con id de mensaje propio."""
    return {
        "id": huella.de_mensaje(origen),
        "codigo": codigo,
        "origen": origen,
        "tipo_origen": tipo_origen,
        "nombre_origen": nombre_origen,
        "ts": time.time(),
        "ttl": config.TTL_INICIAL if ttl is None else ttl,
        "ruta": [],
        "cuerpo": cuerpo,
    }


def validar_datos(m) -> str | None:
    """Validación ESTRUCTURAL del sobre. Devuelve el motivo del fallo o None.

    Solo revisa la forma; el significado del cuerpo es asunto de cada célula.
    """
    if not isinstance(m, dict):
        return "no es un objeto"
    if not es_hash(m.get("id")):
        return "id no es un hash de 64 hex"
    codigo = m.get("codigo")
    if not isinstance(codigo, str) or not codigo:
        return "codigo vacío o no es texto"
    if not isinstance(m.get("origen"), str):
        return "origen no es texto"
    ttl = m.get("ttl")
    if not isinstance(ttl, int) or isinstance(ttl, bool):
        return "ttl no es entero"
    ruta = m.get("ruta")
    if not isinstance(ruta, list) or not all(isinstance(h, str) for h in ruta):
        return "ruta no es lista de hashes"
    if not isinstance(m.get("cuerpo"), dict):
        return "cuerpo no es objeto"
    return None


# --- Control ----------------------------------------------------------------

def hola(entidad: str, hash_: str, nombre: str, servicio: str | None = None,
         escucha: int | None = None) -> dict:
    return {"ctrl": HOLA, "entidad": entidad, "hash": hash_, "nombre": nombre,
            "servicio": servicio, "escucha": escucha, "version": VERSION}


def bienvenida(hash_: str, nombre: str, nodos: list[str]) -> dict:
    return {"ctrl": BIENVENIDA, "hash": hash_, "nombre": nombre, "nodos": nodos}


def pares(nodos: list[str]) -> dict:
    return {"ctrl": PARES, "nodos": nodos}


def rechazo(motivo: str, hash_: str) -> dict:
    return {"ctrl": RECHAZO, "motivo": motivo, "hash": hash_}


def validar_hola(m: dict) -> tuple[str, str] | None:
    """None si el HOLA es aceptable; si no, (motivo de RECHAZO, detalle)."""
    if m.get("version") != VERSION:
        return MOTIVO_VERSION, f"versión {m.get('version')!r}, se esperaba {VERSION}"
    if m.get("entidad") not in ENTIDADES:
        return INVALIDO, f"entidad desconocida {m.get('entidad')!r}"
    if not es_hash(m.get("hash")):
        return INVALIDO, "hash inválido"
    if not isinstance(m.get("nombre"), str) or not m["nombre"]:
        return INVALIDO, "nombre vacío"
    servicio = m.get("servicio")
    if servicio is not None and not isinstance(servicio, str):
        return INVALIDO, "servicio no es texto"
    if m["entidad"] == NODO:
        escucha = m.get("escucha")
        if not isinstance(escucha, int) or isinstance(escucha, bool) or not 0 < escucha < 65536:
            return INVALIDO, "un NODO debe indicar su puerto de escucha"
    return None
