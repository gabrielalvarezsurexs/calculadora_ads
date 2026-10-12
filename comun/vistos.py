"""Registro TEMPORAL de ids ya procesados (§11).

Cada nodo y cada célula tienen uno. Un mensaje cuyo id ya está aquí es un
duplicado: no se procesa ni se retransmite.

Es temporal a propósito: recordar todos los ids para siempre agotaría la
memoria. El costo honesto es que un duplicado que llegue después de la vigencia
volvería a circular; para eso está el TTL, que acota el recorrido de todos
modos.
"""

import threading
import time
from collections import OrderedDict

from comun import config


class RegistroVistos:
    """OrderedDict id -> instante de expiración, en orden de llegada.

    Como la vigencia es la misma para todos, el orden de llegada es también el
    orden de expiración: purgar es sacar del frente mientras esté vencido.
    """

    def __init__(self, vigencia: float | None = None, maximo: int | None = None,
                 reloj=time.monotonic):
        self._vigencia = vigencia
        self._maximo = maximo
        self._reloj = reloj
        self._ids: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.Lock()

    def marcar_si_nuevo(self, id_mensaje: str) -> bool:
        """True si el id es nuevo (y queda registrado); False si es duplicado.

        Es atómico: si dos hilos traen copias del mismo id al mismo tiempo, solo
        uno recibe True, así que solo uno lo reenvía.
        """
        ahora = self._reloj()
        vigencia = self._vigencia if self._vigencia is not None else config.VISTOS_VIGENCIA
        maximo = self._maximo if self._maximo is not None else config.VISTOS_MAX
        with self._lock:
            self._purgar(ahora)
            if id_mensaje in self._ids:
                return False
            self._ids[id_mensaje] = ahora + vigencia
            while len(self._ids) > maximo:
                self._ids.popitem(last=False)
            return True

    def contiene(self, id_mensaje: str) -> bool:
        with self._lock:
            self._purgar(self._reloj())
            return id_mensaje in self._ids

    def __len__(self) -> int:
        with self._lock:
            self._purgar(self._reloj())
            return len(self._ids)

    def _purgar(self, ahora: float) -> None:
        while self._ids:
            expira = next(iter(self._ids.values()))
            if expira > ahora:
                break
            self._ids.popitem(last=False)
