"""Auxiliares de las pruebas de integración: todo en proceso, puertos efímeros.

* ``Registro``: bitácora en memoria (sin consola ni archivo) que permite contar
  eventos y engancharse a ellos, p. ej. "cuando esta célula sea TITULAR…".
* ``Receptor``: célula que solo anota lo que le llega.
* ``Espia``: célula que cuenta los ACK y RES de cada operación (para afirmar
  "exactamente un RES") y que también sirve para inyectar mensajes a mano.
* ``Sistema``: levanta N nodos en malla, servidores e interfaces, y lo apaga.
* ``acortar``: parcha ``comun.config`` mientras vive una clase de pruebas.
"""

import collections
import socket
import threading
import time
from unittest import mock

from celula.base import Celula
from comun import codigos, config, mensajes
from comun.bitacora import Bitacora
from interfaz.nucleo import Interfaz
from nodo.nucleo import Nodo
from servidor.nucleo import Servidor

# Tiempos de prueba. RELEVO se deja en 1 s (plan §12): por debajo, la carga de la
# máquina podría provocar relevos falsos y romper las aserciones de "exactamente uno".
TIEMPOS = {
    "SUPERVISOR": 0.2,
    "BACKOFF_MIN": 0.2,
    "BACKOFF_MAX": 1.0,
    "LATIDO": 0.5,
    "LATIDO_CADUCIDAD": 2.0,
    "VENTANA_ELECCION": 0.3,
    "RELEVO": 1.0,
    "MARGEN_RESULTADO": 1.0,
}


def acortar(caso, **valores) -> None:
    """Desde ``setUpClass``: parcha config hasta que termine la clase."""
    parche = mock.patch.multiple(config, **(valores or TIEMPOS))
    parche.start()
    caso.addClassCleanup(parche.stop)


def esperar(condicion, plazo: float = 10.0, paso: float = 0.05) -> bool:
    fin = time.monotonic() + plazo
    while time.monotonic() < fin:
        if condicion():
            return True
        time.sleep(paso)
    return bool(condicion())


def puertos_libres(n: int) -> list[int]:
    socks = []
    try:
        for _ in range(n):
            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            socks.append(s)
        return [s.getsockname()[1] for s in socks]
    finally:
        for s in socks:
            s.close()


class Registro:
    """Bitácora en memoria. ``bitacora`` es lo que se le pasa a nodos y células."""

    def __init__(self, nombre: str):
        self.nombre = nombre
        self._lock = threading.Lock()
        self.lineas: list[tuple[str, str]] = []
        self.ganchos: list = []  # funciones (evento, texto), llamadas en el hilo que registra
        self.bitacora = Bitacora(nombre, consola=False, archivo=False, callback=self._anotar)

    def _anotar(self, _hora, evento, texto) -> None:
        with self._lock:
            self.lineas.append((evento, texto))
        for gancho in list(self.ganchos):
            gancho(evento, texto)

    def eventos(self, evento: str, contiene: str = "") -> list[str]:
        with self._lock:
            return [t for e, t in self.lineas if e == evento and contiene in t]

    def contar(self, evento: str, contiene: str = "") -> int:
        return len(self.eventos(evento, contiene))


class Receptor(Celula):
    """Anota cada mensaje de datos que le entrega su nodo (ya deduplicado)."""

    def __init__(self, nombre: str, nodo: str):
        self.registro = Registro(nombre)
        super().__init__(mensajes.SONDA, nombre, nodo, bitacora=self.registro.bitacora)
        self.recibidos: list[dict] = []

    def procesar(self, m: dict) -> None:
        self.recibidos.append(m)

    def con_id(self, id_mensaje: str) -> list[dict]:
        return [m for m in list(self.recibidos) if m["id"] == id_mensaje]


class Espia(Celula):
    """Cuenta ACK y RES por operación. También publica mensajes a mano."""

    def __init__(self, nodo: str, nombre: str = "ESPIA"):
        self.registro = Registro(nombre)
        super().__init__(mensajes.SONDA, nombre, nodo, bitacora=self.registro.bitacora)
        self._lock_espia = threading.Lock()
        self.acks = collections.defaultdict(list)  # id_operacion -> [(origen, intento)]
        self.res = collections.defaultdict(list)   # id_operacion -> [mensaje]

    def procesar(self, m: dict) -> None:
        partes = codigos.separar(m["codigo"])
        if partes is None:
            return
        op = m["cuerpo"].get("id_operacion")
        with self._lock_espia:
            if partes[1] == codigos.ACK:
                self.acks[op].append((m["origen"], m["cuerpo"].get("intento")))
            elif partes[1] == codigos.RES:
                self.res[op].append(m)

    def respuestas(self, op: str) -> list[dict]:
        with self._lock_espia:
            return list(self.res.get(op, []))

    def acusadores(self, op: str, intento: int = 1) -> set[str]:
        with self._lock_espia:
            return {o for o, k in self.acks.get(op, []) if k == intento}


class Sistema:
    """N nodos con semillas en cadena + servidores + interfaces, en proceso."""

    def __init__(self):
        self.nodos: list[Nodo] = []
        self.registros: dict[str, Registro] = {}
        self.servidores: list[Servidor] = []
        self.guis: list[Interfaz] = []
        self.celulas: list[Celula] = []

    # ------------------------------------------------------------ construir

    def nodo(self, nombre: str, semillas=(), puerto: int = 0) -> Nodo:
        reg = self.registros[nombre] = Registro(nombre)
        n = Nodo(puerto, nombre, semillas=semillas, bitacora=reg.bitacora)
        n.iniciar()
        self.nodos.append(n)
        return n

    def malla(self, n: int = 4) -> list[Nodo]:
        """Semillas en cadena: cada nodo solo conoce al anterior."""
        for k in range(1, n + 1):
            semillas = [self.nodos[-1].endpoint] if self.nodos else []
            self.nodo(f"Nodo {k}", semillas)
        return list(self.nodos)

    def servidor(self, servicio: str, nodo: Nodo, nombre: str | None = None,
                 retardo_ms: int = 0) -> Servidor:
        nombre = nombre or f"{servicio}@{nodo.puerto}"
        reg = self.registros[nombre] = Registro(nombre)
        s = Servidor(servicio, nombre, nodo.endpoint, retardo_ms=retardo_ms,
                     bitacora=reg.bitacora)
        s.iniciar()
        self.servidores.append(s)
        self.celulas.append(s)
        return s

    def gui(self, nombre: str, nodo: Nodo, acuses_min: int | None = None) -> Interfaz:
        reg = self.registros[nombre] = Registro(nombre)
        g = Interfaz(nombre, nodo.endpoint, acuses_min=acuses_min, bitacora=reg.bitacora)
        g.iniciar()
        self.guis.append(g)
        self.celulas.append(g)
        return g

    def agregar(self, celula: Celula) -> Celula:
        celula.iniciar()
        self.celulas.append(celula)
        return celula

    def completo(self, n_nodos: int = 4) -> "Sistema":
        """Malla de n + en cada nodo 1 GUI y los 4 servidores (configuración mínima)."""
        self.malla(n_nodos)
        assert self.esperar_malla(), "la malla no se formó"
        for k, nodo in enumerate(self.nodos, 1):
            for s in codigos.SERVICIOS:
                self.servidor(s, nodo, f"{s}-N{k}")
        for k, nodo in enumerate(self.nodos, 1):
            self.gui(f"GUI-{k}", nodo)
        assert self.esperar_disponible(len(self.nodos)), "las GUIs no vieron a los servidores"
        return self

    # ---------------------------------------------------------------- esperas

    def esperar_malla(self, plazo: float = 15.0) -> bool:
        def lista():
            vivos = [n for n in self.nodos if n.activo]
            hashes = {n.hash for n in vivos}
            return all(set(n.vecinos) == hashes - {n.hash} for n in vivos)
        return esperar(lista, plazo)

    def esperar_disponible(self, vivas: int, plazo: float = 15.0) -> bool:
        return esperar(lambda: all(d["vivas"] == vivas for g in self.guis
                                   for d in g.disponibilidad().values()), plazo)

    # ---------------------------------------------------------------- apagar

    def apagar(self) -> None:
        for c in self.celulas:
            c.detener()
        for n in self.nodos:
            n.detener()
