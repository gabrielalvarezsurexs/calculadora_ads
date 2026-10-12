"""Transporte: NDJSON (un JSON por línea) sobre TCP, y el Enlace.

Adaptado del primer parcial, con tres cambios que la malla necesita:

1. **Lector tolerante.** El lector anterior hacía ``json.loads`` dentro del
   generador: una sola línea inválida lanzaba, terminaba el generador y con él
   cerraba la conexión. Aquí cada línea se decodifica por separado; una
   inválida se reporta y la lectura sigue. Una línea de más de ``MAX_LINEA``
   bytes se descarta completa.
2. **Sin NaN ni Infinity.** Se serializa con ``allow_nan=False`` y se rechazan
   al leer: no son JSON estándar.
3. **Enlace con cola de escritura.** Quien difunde solo encola bytes; un hilo
   escritor por enlace hace el ``sendall``. Así un par lento o colgado nunca
   congela la inundación hacia los demás. Si la cola se desborda, el enlace se
   da por muerto (LENTO).
"""

import json
import queue
import socket
import threading
import time
import traceback

from comun import config


class ConexionCerrada(Exception):
    """El par cerró la conexión (recv devolvió b'')."""


def serializar(mensaje: dict) -> bytes:
    linea = json.dumps(mensaje, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return (linea + "\n").encode("utf-8")


def enviar(sock: socket.socket, mensaje: dict) -> None:
    sock.sendall(serializar(mensaje))


def _rechazar_constante(nombre):
    raise ValueError(f"{nombre} no es JSON estándar")


def _decodificar(linea: bytes):
    try:
        objeto = json.loads(linea.decode("utf-8"), parse_constant=_rechazar_constante)
    except (UnicodeDecodeError, ValueError):
        return None, "no es JSON"
    if not isinstance(objeto, dict):
        return None, "no es un objeto JSON"
    return objeto, None


def leer_mensajes(fuente):
    """Generador de pares (mensaje, problema); exactamente uno es None.

    Recibe cualquier objeto con ``.recv(n)``, para poder probar el framing con
    una fuente falsa. Termina con ConexionCerrada cuando el par cierra.
    """
    buffer = b""
    descartando = False  # estamos tirando el resto de una línea demasiado larga
    while True:
        trozo = fuente.recv(65536)
        if not trozo:
            raise ConexionCerrada()
        buffer += trozo
        while True:
            pos = buffer.find(b"\n")
            if pos < 0:
                break
            linea, buffer = buffer[:pos], buffer[pos + 1:]
            if descartando:
                descartando = False
                continue
            linea = linea.strip()
            if not linea:
                continue
            if len(linea) > config.MAX_LINEA:
                yield None, f"línea de {len(linea)} bytes (máx. {config.MAX_LINEA})"
                continue
            yield _decodificar(linea)
        if len(buffer) > config.MAX_LINEA:
            buffer = b""
            if not descartando:
                descartando = True
                yield None, f"más de {config.MAX_LINEA} bytes sin salto de línea"


_CERRAR = object()  # marca en la cola: cerrar el socket después de vaciarla


class Enlace:
    """Un socket con su hilo lector y su hilo escritor.

    El dueño (nodo o célula) pasa callbacks que corren en el hilo lector:
    ``al_mensaje(enlace, dict)``, ``al_problema(enlace, texto)`` y
    ``al_cerrar(enlace, motivo)``. ``al_cerrar`` se llama exactamente una vez.
    Una excepción dentro de un callback se registra y la lectura sigue.

    Los atributos de identidad (entidad, hash, nombre, servicio) los llena el
    dueño cuando el par se presenta.
    """

    def __init__(self, sock: socket.socket, saliente: bool, endpoint: str | None = None, *,
                 al_mensaje, al_problema=None, al_cerrar=None, bitacora=None,
                 etiqueta: str = "enlace"):
        self.sock = sock
        self.saliente = saliente          # True si lo iniciamos nosotros (marcamos)
        self.endpoint = endpoint
        self.entidad: str | None = None
        self.hash: str | None = None
        self.nombre: str | None = None
        self.servicio: str | None = None
        self.presentado = False
        self.desde = time.time()
        self.motivo_cierre: str | None = None
        try:
            self.ip_par, self.puerto_par = sock.getpeername()[:2]
        except OSError:
            self.ip_par, self.puerto_par = None, None

        self._al_mensaje = al_mensaje
        self._al_problema = al_problema
        self._al_cerrar = al_cerrar
        self._bitacora = bitacora
        self._etiqueta = etiqueta
        self._cola: queue.Queue = queue.Queue()
        self._vivo = True
        self._lock = threading.Lock()
        self._lector = threading.Thread(target=self._leer, name=f"{etiqueta}-lector",
                                        daemon=True)
        self._escritor = threading.Thread(target=self._escribir, name=f"{etiqueta}-escritor",
                                          daemon=True)

    @property
    def iniciador(self) -> str:
        return "yo" if self.saliente else "par"

    @property
    def vivo(self) -> bool:
        return self._vivo

    def iniciar(self) -> "Enlace":
        """Arranca los hilos. Va aparte del constructor para que el dueño pueda
        registrar el enlace en sus tablas antes de que llegue el primer mensaje."""
        self._escritor.start()
        self._lector.start()
        return self

    # --- Escritura ----------------------------------------------------------

    def enviar(self, mensaje: dict) -> bool:
        return self.enviar_bytes(serializar(mensaje))

    def enviar_bytes(self, datos: bytes) -> bool:
        """Encola y regresa de inmediato. False si el enlace ya no sirve."""
        if not self._vivo:
            return False
        if self._cola.qsize() >= config.COLA_ENLACE_MAX:
            self.cerrar(f"LENTO: {config.COLA_ENLACE_MAX} mensajes sin enviar")
            return False
        self._cola.put(datos)
        return True

    def _escribir(self) -> None:
        while True:
            datos = self._cola.get()
            if datos is None:
                return
            if datos is _CERRAR:
                self._cerrar_socket()
                return
            try:
                self.sock.sendall(datos)
            except OSError as e:
                self.cerrar(f"error de escritura: {e}")
                return

    # --- Lectura ------------------------------------------------------------

    def _leer(self) -> None:
        motivo = "cerrado por el par"
        try:
            for mensaje, problema in leer_mensajes(self.sock):
                if not self._vivo:
                    break
                try:
                    if problema is not None:
                        if self._al_problema:
                            self._al_problema(self, problema)
                    else:
                        self._al_mensaje(self, mensaje)
                except Exception:
                    self._error("callback")
        except ConexionCerrada:
            pass
        except OSError as e:
            motivo = f"error de lectura: {e}"
        except Exception:
            self._error("lector")
            motivo = "error interno del lector"
        finally:
            self.cerrar(motivo)
            if self._al_cerrar:
                try:
                    self._al_cerrar(self, self.motivo_cierre)
                except Exception:
                    self._error("al_cerrar")

    # --- Cierre -------------------------------------------------------------

    def cerrar(self, motivo: str | None = None, vaciar: bool = False) -> None:
        """Cierra el enlace. Con ``vaciar=True`` primero envía lo encolado
        (por ejemplo, un RECHAZO) y luego cierra. Idempotente: gana el primer
        motivo."""
        with self._lock:
            if not self._vivo:
                return
            self._vivo = False
            self.motivo_cierre = motivo
        if vaciar:
            self._cola.put(_CERRAR)
            # Red de seguridad por si el escritor está atorado con un par colgado.
            t = threading.Timer(2.0, self._cerrar_socket)
            t.daemon = True
            t.start()
        else:
            self._cerrar_socket()
            self._cola.put(None)

    def _cerrar_socket(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def esperar(self, timeout: float | None = None) -> None:
        """Espera a que terminen los hilos (útil para herramientas de CLI)."""
        self._escritor.join(timeout)
        self._lector.join(timeout)

    def _error(self, donde: str) -> None:
        texto = f"{self._etiqueta} ({donde}): {traceback.format_exc()}"
        if self._bitacora:
            self._bitacora("ERROR", texto)
        else:
            print(texto, flush=True)
