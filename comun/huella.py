"""Identificadores únicos (SHA-256) y el ranking de elección.

TODO en el sistema tiene un hash: nodos, células, mensajes y operaciones.
Cada entidad genera el suyo al arrancar y lo presenta en su HOLA; nadie
asigna identidades, así que no hay un punto central que pueda fallar.

Unicidad: cada hash mezcla 128 bits aleatorios, el reloj en nanosegundos, un
contador por proceso, el pid y el host. La probabilidad de colisión es del
orden de 2^-128, y el contador garantiza unicidad dentro del proceso aunque el
reloj devuelva el mismo valor dos veces.
"""

import hashlib
import itertools
import os
import secrets
import socket
import threading
import time

_HOST = socket.gethostname()
_PID = os.getpid()
_contador = itertools.count()
_lock = threading.Lock()


def generar(tipo: str, *datos) -> str:
    """Hash nuevo e irrepetible: 64 caracteres hexadecimales."""
    with _lock:
        n = next(_contador)
    partes = [tipo, *map(str, datos), _HOST, str(_PID), str(time.time_ns()), str(n),
              secrets.token_hex(16)]
    return hashlib.sha256("|".join(partes).encode("utf-8")).hexdigest()


def de_entidad(entidad: str, nombre: str, servicio: str | None = None) -> str:
    return generar("entidad", entidad, nombre, servicio or "")


def de_mensaje(origen: str) -> str:
    return generar("mensaje", origen)


def de_operacion(interfaz: str, servicio: str, a, b) -> str:
    return generar("operacion", interfaz, servicio, a, b)


def corto(h: str | None) -> str:
    """Solo para mostrar. La identidad es siempre el hash completo."""
    return (h or "")[:8]


def prioridad(celula: str, id_operacion: str, intento: int) -> str:
    """Peso de una célula para una ronda (rendezvous hashing / HRW).

    Es determinista: cualquier célula que conozca el mismo conjunto de
    acusadores calcula el mismo orden, sin intercambiar mensajes. El intento
    entra al hash, así que un reintento puede tocarle a otra titular.
    """
    return hashlib.sha256(f"{celula}|{id_operacion}|{intento}".encode()).hexdigest()


def ranking(celulas, id_operacion: str, intento: int) -> list[str]:
    """Células ordenadas de titular a último respaldo.

    El desempate por hash de célula es imposible en la práctica (dos SHA-256
    iguales), pero deja el orden definido pase lo que pase.
    """
    return sorted(celulas, key=lambda c: (prioridad(c, id_operacion, intento), c))
