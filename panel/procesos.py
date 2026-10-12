"""Lanzar, vigilar y tumbar procesos del sistema operativo. Sin Tkinter.

Esto NO es parte del sistema ADS: solo ahorra teclear comandos en la demo.
Cada proceso se lanza con el mismo comando que se podría escribir a mano
(``py -m nodo ...``, ``py -m servidor ...``) y el panel lo muestra tal cual.

Un hilo lector por proceso vacía su stdout. Sin él, el pipe se llenaría y el
hijo se bloquearía al escribir su bitácora.
"""

import os
import random
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from comun import codigos

RAIZ = Path(__file__).resolve().parent.parent
PUERTO_BASE = 5000
MAX_LINEAS = 2000

NODO = "Nodo"
GUI = "GUI"
COLUMNAS = (NODO, GUI, *codigos.SERVICIOS)  # columnas de la matriz del panel


def puerto(k: int) -> int:
    return PUERTO_BASE + k


def endpoint(k: int) -> str:
    return f"127.0.0.1:{puerto(k)}"


@dataclass
class Proceso:
    nombre: str
    tipo: str          # NODO, GUI o un servicio (SUM, SUB, MUL, DIV)
    fila: int          # número de nodo al que pertenece
    comando: list[str]
    popen: subprocess.Popen
    inicio: float = field(default_factory=time.time)
    lineas: deque = field(default_factory=lambda: deque(maxlen=MAX_LINEAS))
    total_lineas: int = 0  # para que el visor sepa cuántas líneas nuevas hay
    tumbado: bool = False  # lo terminó el panel (en Windows su código queda en 1)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def agregar_linea(self, linea: str) -> None:
        with self._lock:
            self.lineas.append(linea)
            self.total_lineas += 1

    def lineas_desde(self, vistas: int | None) -> tuple[list[str], int]:
        """Las líneas posteriores a las ``vistas`` (todas si es None) y el total actual."""
        with self._lock:
            total = self.total_lineas
            if vistas is None:
                return list(self.lineas), total
            n = min(total - vistas, len(self.lineas))
            return (list(self.lineas)[-n:] if n > 0 else []), total

    @property
    def pid(self) -> int:
        return self.popen.pid

    @property
    def codigo(self) -> int | None:
        return self.popen.poll()

    @property
    def vivo(self) -> bool:
        return self.popen.poll() is None

    @property
    def estado(self) -> str:
        c = self.codigo
        if c is None:
            return "vivo"
        return "tumbado" if self.tumbado else f"terminado ({c})"

    def comando_legible(self) -> str:
        partes = ["py", *self.comando[2:]]  # [python, -u, -m, ...] -> py -m ...
        return " ".join(f'"{p}"' if " " in p else p for p in partes)


class Gestor:
    def __init__(self, raiz: Path = RAIZ):
        self.raiz = raiz
        self.procesos: list[Proceso] = []
        self._lock = threading.Lock()
        self._instancias: dict[tuple[int, str], int] = {}

    # ---------------------------------------------------------------- consulta

    def vivos(self, fila: int | None = None, tipo: str | None = None) -> list[Proceso]:
        with self._lock:
            return [p for p in self.procesos if p.vivo
                    and (fila is None or p.fila == fila) and (tipo is None or p.tipo == tipo)]

    def filas(self) -> list[int]:
        """Números de nodo que han existido (las filas de la matriz)."""
        with self._lock:
            return sorted({p.fila for p in self.procesos})

    # ---------------------------------------------------------------- lanzar

    def lanzar_nodo(self, k: int, geometria: str | None = None) -> Proceso:
        """Lanza el nodo k. Su semilla es un nodo vivo elegido AL AZAR (ninguno si es el
        primero): demuestra que basta conocer a cualquiera y que ningún nodo es especial."""
        otros = [p.fila for p in self.vivos(tipo=NODO) if p.fila != k]
        args = ["nodo", "--puerto", str(puerto(k)), "--nombre", f"Nodo {k}"]
        if otros:
            args += ["--semillas", endpoint(random.choice(otros))]
        if geometria:
            args += ["--geometria", geometria]
        return self._lanzar(f"Nodo {k}", NODO, k, args)

    def lanzar_celula(self, k: int, tipo: str, *, retardo_ms: int = 0,
                      geometria: str | None = None) -> Proceso:
        n = self._instancias.get((k, tipo), 0)
        self._instancias[(k, tipo)] = n + 1
        sufijo = "" if n == 0 else chr(ord("a") + n)  # SUM-N2, SUM-N2b, SUM-N2c...
        if tipo == GUI:
            nombre = f"GUI-{k}{sufijo}"
            args = ["interfaz", "--nodo", endpoint(k), "--nombre", nombre]
            if geometria:
                args += ["--geometria", geometria]
        else:
            nombre = f"{tipo}-N{k}{sufijo}"
            args = ["servidor", "--servicio", tipo, "--nodo", endpoint(k), "--nombre", nombre]
            if retardo_ms:
                args += ["--retardo-ms", str(retardo_ms)]
        return self._lanzar(nombre, tipo, k, args)

    def _lanzar(self, nombre: str, tipo: str, fila: int, args: list[str]) -> Proceso:
        comando = [sys.executable, "-u", "-m", *args]
        popen = subprocess.Popen(
            comando, cwd=self.raiz, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        proceso = Proceso(nombre, tipo, fila, comando, popen)
        with self._lock:
            self.procesos.append(proceso)
        threading.Thread(target=_leer, args=(proceso,), name=f"lector-{nombre}",
                         daemon=True).start()
        return proceso

    # ---------------------------------------------------------------- tumbar

    def tumbar(self, proceso: Proceso) -> None:
        """Simula una caída: terminate() sin avisarle a nadie."""
        if proceso.vivo:
            proceso.tumbado = True
            try:
                proceso.popen.terminate()
            except OSError:
                pass

    def tumbar_reciente(self, fila: int, tipo: str) -> Proceso | None:
        vivos = self.vivos(fila, tipo)
        if not vivos:
            return None
        proceso = max(vivos, key=lambda p: p.inicio)
        self.tumbar(proceso)
        return proceso

    def detener_todo(self) -> None:
        vivos = self.vivos()
        for p in vivos:
            self.tumbar(p)
        for p in vivos:
            try:
                p.popen.wait(3)
            except subprocess.TimeoutExpired:
                p.popen.kill()


def _leer(proceso: Proceso) -> None:
    try:
        for linea in proceso.popen.stdout:
            proceso.agregar_linea(linea.rstrip("\n"))
    except (OSError, ValueError):
        pass
