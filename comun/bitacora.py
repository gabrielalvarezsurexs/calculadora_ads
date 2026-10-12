"""Bitácora de cada proceso: consola + archivo + callback opcional para la GUI.

Formato: ``HH:MM:SS.mmm [EVENTO] texto``.

Nunca lanza excepciones. Si el panel que leía la consola se cierra, escribir
en el pipe roto falla; eso se ignora y el archivo sigue creciendo, así que el
proceso sobrevive al panel. Los colores ANSI solo se usan en una terminal de
verdad, para que el panel no muestre códigos basura.
"""

import re
import sys
import threading
import time
from pathlib import Path

CARPETA_LOGS = Path(__file__).resolve().parent.parent / "logs"

_COLORES = {
    "ERROR": "\033[91m", "DROP": "\033[91m", "LENTO": "\033[91m", "RECHAZO": "\033[91m",
    "DUP": "\033[93m", "TTL": "\033[93m", "INALCANZABLE": "\033[93m",
    "FWD": "\033[96m", "CONEXION": "\033[92m", "DESCONEXION": "\033[95m",
    "INICIO": "\033[1m",
}
_FIN = "\033[0m"


def hora() -> str:
    t = time.time()
    return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int(t * 1000) % 1000:03d}"


def _nombre_archivo(nombre: str, hash_: str | None) -> str:
    base = re.sub(r"[^\w.-]+", "_", nombre).strip("_") or "proceso"
    return f"{base}-{hash_[:8]}.log" if hash_ else f"{base}.log"


class Bitacora:
    def __init__(self, nombre: str, hash_: str | None = None, *, consola: bool = True,
                 archivo: bool = True, callback=None, carpeta: Path | None = None):
        self.nombre = nombre
        self.callback = callback
        self._consola = consola
        self._lock = threading.Lock()
        self._color = consola and _es_terminal()
        self._archivo = None
        self.ruta = None
        if archivo:
            try:
                carpeta = carpeta or CARPETA_LOGS
                carpeta.mkdir(parents=True, exist_ok=True)
                self.ruta = carpeta / _nombre_archivo(nombre, hash_)
                self._archivo = open(self.ruta, "a", encoding="utf-8")
            except OSError:
                self._archivo = None

    def __call__(self, evento: str, texto: str = "", *, consola: bool = True) -> None:
        self.registrar(evento, texto, consola=consola)

    def registrar(self, evento: str, texto: str = "", *, consola: bool = True) -> None:
        h = hora()
        linea = f"{h} [{evento}] {texto}"
        with self._lock:
            if self._consola and consola:
                try:
                    if self._color and evento in _COLORES:
                        sys.stdout.write(f"{h} {_COLORES[evento]}[{evento}]{_FIN} {texto}\n")
                    else:
                        sys.stdout.write(linea + "\n")
                    sys.stdout.flush()
                except (OSError, ValueError, AttributeError):
                    pass
            if self._archivo is not None:
                try:
                    self._archivo.write(linea + "\n")
                    self._archivo.flush()
                except (OSError, ValueError):
                    pass
        if self.callback is not None:
            try:
                self.callback(h, evento, texto)
            except Exception:
                pass

    def cerrar(self) -> None:
        with self._lock:
            if self._archivo is not None:
                try:
                    self._archivo.close()
                except OSError:
                    pass
                self._archivo = None


def _es_terminal() -> bool:
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def preparar_consola() -> None:
    """Regla 5 del proyecto: UTF-8 en consola, sin reventar por un caracter raro."""
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
