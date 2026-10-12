"""Célula base: lo común a toda célula del sistema (el ACP de ADS).

Una célula no sabe quién más existe ni a quién le habla. Se conecta a UN nodo
del Campo de Datos, se presenta, publica mensajes con Código de Contenido y
recibe TODO lo que el nodo inunda; luego decide por código qué le interesa.

Lo que resuelve esta clase, para que el servidor y la GUI solo pongan su lógica:

* **Conexión.** Marca a su nodo, manda HOLA y espera BIENVENIDA
  (``BIENVENIDA_TIMEOUT``). Hasta entonces no publica nada.
* **Candidatos.** Guarda la lista de nodos que le dio la BIENVENIDA y la
  actualiza con cada PARES: es su plan de escape.
* **Failover.** Si se cae el enlace, reintenta ``REINTENTOS_MISMO_NODO`` veces
  con su nodo (1 s entre intentos) y luego rota por los demás candidatos. Si
  nadie responde en una vuelta completa, espera con backoff y empieza otra. Si
  su nodo original revive, no regresa a él (para no oscilar). El hash de la
  célula se conserva: para el sistema sigue siendo la misma célula.
* **Deduplicación propia** (4ª defensa del §11): su propio ``RegistroVistos``
  descarta copias que pueden llegar repetidas después de un failover.
* **Publicar sin conexión** devuelve None y se registra; ese mensaje se pierde
  y lo absorben los reintentos de la GUI.

Las subclases implementan ``procesar(m)`` y, si quieren, ``al_conectar`` y
``al_desconectar``. ``procesar`` corre en el hilo lector del enlace.
"""

import socket
import threading

from comun import config, huella, mensajes
from comun.bitacora import Bitacora
from comun.protocolo import Enlace
from comun.vistos import RegistroVistos

# Cómo se recuperó la conexión (lo recibe al_conectar).
CONEXION = "conexion"      # primera vez
RECONEXION = "reconexion"  # se cayó y volvió al mismo nodo
FAILOVER = "failover"      # se cayó y se pasó a otro nodo


class Celula:
    def __init__(self, entidad: str, nombre: str, nodo: str, servicio: str | None = None, *,
                 bitacora: Bitacora | None = None, eventos=None):
        ep = mensajes.endpoint(*mensajes.separar_endpoint(nodo))  # ValueError si no sirve
        self.entidad = entidad
        self.nombre = nombre
        self.servicio = servicio
        self.hash = huella.de_entidad(entidad, nombre, servicio)
        self.bitacora = bitacora or Bitacora(nombre, self.hash)
        self.eventos = eventos

        self._lock = threading.Lock()
        self._enlace: Enlace | None = None
        self.nodo_actual: dict | None = None   # {"hash", "nombre", "endpoint"}
        self.nodo_inicial = ep                 # el --nodo con que arrancó (solo para mostrar)
        self._ep_actual = ep                   # a quién se marca primero
        self.candidatos: list[str] = [ep]      # endpoints de nodos para el failover
        self.vistos = RegistroVistos()
        self.contadores = {"recibidos": 0, "duplicados": 0, "publicados": 0, "perdidos": 0}

        self._activo = threading.Event()
        self._parar = threading.Event()   # interrumpe las esperas al detener
        self._caido = threading.Event()   # despierta al hilo conector

    # ------------------------------------------------------------------ vida

    def iniciar(self) -> None:
        self._activo.set()
        self.log("INICIO", f"{self.entidad} {self.nombre} · {huella.corto(self.hash)}"
                           f"{' · ' + self.servicio if self.servicio else ''}"
                           f" · nodo inicial {self._ep_actual}")
        threading.Thread(target=self._mantener, name=f"{self.nombre}-conector",
                         daemon=True).start()

    def detener(self) -> None:
        if not self._activo.is_set():
            return
        self._activo.clear()
        self._parar.set()
        self._caido.set()
        with self._lock:
            enlace = self._enlace
        if enlace is not None:
            enlace.cerrar("célula detenida")
        self.log("FIN", f"{self.nombre} detenida")

    @property
    def activo(self) -> bool:
        return self._activo.is_set()

    @property
    def conectado(self) -> bool:
        with self._lock:
            return self._enlace is not None and self._enlace.vivo

    # --------------------------------------------------- hooks de subclases

    def procesar(self, m: dict) -> None:
        """Un mensaje de datos nuevo (ya validado y deduplicado)."""

    def al_conectar(self, nodo: dict, como: str) -> None:
        """Se acaba de registrar en un nodo. ``como``: CONEXION, RECONEXION o FAILOVER."""

    def al_desconectar(self, motivo: str | None) -> None:
        """Se perdió el enlace con su nodo; el conector ya está buscando otro."""

    # ------------------------------------------------------------- publicar

    def publicar(self, codigo: str, cuerpo: dict, *, ttl: int | None = None) -> dict | None:
        """Publica un mensaje de datos (broadcast). Devuelve el sobre enviado, o
        None si no hay conexión al Campo de Datos (el mensaje se pierde)."""
        m = mensajes.nuevo(codigo, self.hash, self.entidad, self.nombre, cuerpo, ttl)
        self.vistos.marcar_si_nuevo(m["id"])  # si alguna copia regresa, es duplicado
        with self._lock:
            enlace = self._enlace
        if enlace is None or not enlace.enviar(m):
            self.contadores["perdidos"] += 1
            if codigo not in config.CODIGOS_SILENCIOSOS:
                self.log("PERDIDO", f"{codigo} {huella.corto(m['id'])} no salió: "
                                    f"sin conexión al Campo de Datos")
            return None
        self.contadores["publicados"] += 1
        return m

    # ------------------------------------------------------------- conexión

    def _mantener(self) -> None:
        """Hilo conector: conecta, y cada vez que se cae el enlace, hace failover."""
        while self._activo.is_set():
            try:
                if self.conectado:
                    self._caido.wait(1.0)
                    self._caido.clear()
                    continue
                self._recuperar()
            except Exception as e:
                self.log("ERROR", f"conector: {e!r}")
                self._parar.wait(1.0)

    def _recuperar(self) -> None:
        anterior = self.nodo_actual
        backoff = config.BACKOFF_MIN
        vuelta = 0
        while self._activo.is_set():
            origen = self._ep_actual
            if anterior is not None and vuelta == 0:
                # Recién caído: unos reintentos rápidos con el mismo nodo, por si fue un
                # parpadeo. Timeout corto: si de verdad murió, no hay que esperar al SO.
                plan = [(origen, 1.0, config.REINTENTO_TIMEOUT)] * config.REINTENTOS_MISMO_NODO
            else:
                plan = [(origen, 0.0, config.CONECTAR_TIMEOUT)]
            plan += [(ep, 0.0, config.CONECTAR_TIMEOUT) for ep in self._rotacion(origen)]

            for ep, espera, timeout in plan:
                if espera and self._parar.wait(espera):
                    return
                if not self._activo.is_set():
                    return
                ok, problema = self._intentar(ep, timeout)
                if ok:
                    self._conectado(anterior, ep)
                    return
                self.log("INALCANZABLE", f"{ep}: {problema}")

            vuelta += 1
            self.log("SIN_CAMPO", f"ningún nodo respondió (vuelta {vuelta}); "
                                  f"nueva vuelta en {backoff:.0f} s")
            self._emitir("conexion", {"estado": "sin_campo", "texto": "sin Campo de Datos"})
            if self._parar.wait(backoff):
                return
            backoff = min(backoff * 2, config.BACKOFF_MAX)

    def _rotacion(self, origen: str) -> list[str]:
        """Los demás candidatos en round-robin, empezando después de ``origen``."""
        with self._lock:
            lista = sorted(set(self.candidatos))
        if origen in lista:
            i = lista.index(origen)
            lista = lista[i + 1:] + lista[:i]
        return [ep for ep in lista if ep != origen]

    def _intentar(self, ep: str, timeout: float) -> tuple[bool, str | None]:
        try:
            host, puerto = mensajes.separar_endpoint(ep)
            sock = socket.create_connection((host, puerto), timeout=timeout)
            sock.settimeout(None)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except (OSError, ValueError) as e:
            return False, str(e)
        enlace = Enlace(sock, saliente=True, endpoint=ep, al_mensaje=self._al_mensaje,
                        al_problema=self._al_problema, al_cerrar=self._al_cerrar,
                        bitacora=self.bitacora, etiqueta=self.nombre)
        enlace.respuesta = threading.Event()
        enlace.rechazo = None
        enlace.enviar(mensajes.hola(self.entidad, self.hash, self.nombre, self.servicio))
        enlace.iniciar()
        if not enlace.respuesta.wait(config.BIENVENIDA_TIMEOUT):
            enlace.cerrar("sin BIENVENIDA")
            return False, "no contestó el HOLA"
        if not enlace.presentado:
            if enlace.rechazo:
                return False, f"RECHAZO({enlace.rechazo})"
            return False, enlace.motivo_cierre or "se cerró antes de la BIENVENIDA"
        if not self._activo.is_set():
            enlace.cerrar("célula detenida")
            return False, "célula detenida"
        return True, None

    def _conectado(self, anterior: dict | None, ep: str) -> None:
        nodo = self.nodo_actual
        self._ep_actual = ep
        if anterior is None:
            como, evento = CONEXION, "CONEXION"
        elif anterior["hash"] == nodo["hash"]:
            como, evento = RECONEXION, "RECONEXION"
        else:
            como, evento = FAILOVER, "FAILOVER"
        flecha = "→ " if como == FAILOVER else ""
        self.log(evento, f"{flecha}{nodo['nombre']} ({huella.corto(nodo['hash'])}) en {ep}"
                         f" · candidatos: {', '.join(self.candidatos)}")
        self._emitir("conexion", {"estado": como, "nodo": nodo["nombre"], "endpoint": ep})
        try:
            self.al_conectar(dict(nodo), como)
        except Exception as e:
            self.log("ERROR", f"al_conectar: {e!r}")

    # --------------------------------------------------- callbacks del enlace

    def _al_mensaje(self, enlace: Enlace, m: dict) -> None:
        ctrl = m.get("ctrl")
        if not enlace.presentado:
            if ctrl == mensajes.BIENVENIDA:
                self._bienvenida(enlace, m)
            elif ctrl == mensajes.RECHAZO:
                enlace.rechazo = str(m.get("motivo"))
                enlace.cerrar(f"RECHAZO {enlace.rechazo}")
                enlace.respuesta.set()
            return  # nada se procesa antes de la BIENVENIDA
        if ctrl == mensajes.PARES:
            self._agregar_candidatos(m.get("nodos"))
            return
        if ctrl == mensajes.RECHAZO:
            enlace.cerrar(f"RECHAZO {m.get('motivo')}")
            return
        if ctrl is not None:
            return
        self._recibir(m)

    def _bienvenida(self, enlace: Enlace, m: dict) -> None:
        h, nombre = m.get("hash"), m.get("nombre")
        if not mensajes.es_hash(h) or not isinstance(nombre, str):
            enlace.cerrar("BIENVENIDA inválida")
            enlace.respuesta.set()
            return
        enlace.entidad, enlace.hash, enlace.nombre = mensajes.NODO, h, nombre
        with self._lock:
            if self._enlace is not None and self._enlace.vivo:
                viejo_vivo = True
            else:
                viejo_vivo = False
                enlace.presentado = True
                self._enlace = enlace
                self.nodo_actual = {"hash": h, "nombre": nombre, "endpoint": enlace.endpoint}
        if viejo_vivo:  # no debería pasar: solo se marca sin conexión
            enlace.cerrar("ya hay un enlace vivo")
        else:
            self._agregar_candidatos(m.get("nodos"))
        enlace.respuesta.set()

    def _agregar_candidatos(self, nodos) -> None:
        nuevos = mensajes.endpoints_validos(nodos)
        with self._lock:
            antes = set(self.candidatos)
            self.candidatos = sorted(antes | set(nuevos))
            crecio = len(self.candidatos) > len(antes)
        if crecio:
            self.log("CANDIDATOS", f"nodos para failover: {', '.join(self.candidatos)}",
                     consola=False)

    def _al_problema(self, enlace: Enlace, problema: str) -> None:
        self.log("DROP", f"línea de {enlace.nombre or enlace.endpoint}: {problema}")

    def _al_cerrar(self, enlace: Enlace, motivo: str | None) -> None:
        if hasattr(enlace, "respuesta"):
            enlace.respuesta.set()
        with self._lock:
            era_actual = self._enlace is enlace
            if era_actual:
                self._enlace = None
        if not era_actual:
            return
        if self._activo.is_set():
            self.log("DESCONEXION", f"se perdió {enlace.nombre} ({motivo or 'sin motivo'}); "
                                    f"buscando nodo…")
            self._emitir("conexion", {"estado": "caida", "nodo": enlace.nombre})
        self._caido.set()
        try:
            self.al_desconectar(motivo)
        except Exception as e:
            self.log("ERROR", f"al_desconectar: {e!r}")

    def _recibir(self, m: dict) -> None:
        motivo = mensajes.validar_datos(m)
        if motivo:
            self.log("DROP", f"mensaje inválido: {motivo}")
            return
        if m["origen"] == self.hash:
            return  # eco de algo que yo publiqué
        if not self.vistos.marcar_si_nuevo(m["id"]):
            self.contadores["duplicados"] += 1
            self.log("DUP", f"{m['codigo']} {huella.corto(m['id'])} ya procesado; se descarta",
                     consola=m["codigo"] not in config.CODIGOS_SILENCIOSOS)
            return
        self.contadores["recibidos"] += 1
        self.procesar(m)

    # ------------------------------------------------------------- utilidades

    def log(self, evento: str, texto: str, *, consola: bool = True) -> None:
        self.bitacora(evento, texto, consola=consola)

    def _emitir(self, tipo: str, datos) -> None:
        if self.eventos is not None:
            self.eventos.put((tipo, datos))
