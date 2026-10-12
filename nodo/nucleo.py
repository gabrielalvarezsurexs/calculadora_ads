"""Nodo del Campo de Datos.

Un nodo es "bobo" a propósito: acepta conexiones, identifica qué tipo de
entidad se presenta, forma la malla con los demás nodos y difunde (inunda)
cada mensaje de datos evitando ciclos y duplicados. NUNCA abre el ``cuerpo`` ni
conoce el catálogo de Códigos de Contenido: la decisión de qué hacer con un
mensaje es de las células.

Protocolo de conexión (§10.1), resumido:

* Toda entidad se presenta con HOLA (tipo, hash, nombre, versión). Un NODO
  va a ``vecinos``; una célula (INTERFAZ, SERVIDOR o SONDA) va a ``celulas``.
* El nodo contesta BIENVENIDA con los endpoints de nodos que conoce, y manda
  PARES a todos sus enlaces cada vez que ese conjunto crece (gossip).
* Un supervisor marca a cada endpoint conocido que aún no tenga enlace. Basta
  conocer UN nodo cualquiera para terminar en malla completa.
* Si dos nodos se marcan a la vez, la regla de enlace duplicado (que solo
  depende de los hashes y de quién inició cada enlace) hace que ambos lados se
  queden con el mismo.

Este módulo no importa Tkinter. Si se le pasa una ``queue.Queue`` en
``eventos``, empuja ahí lo que la ventana necesita mostrar.
"""

import re
import socket
import threading
import time

from comun import config, huella, mensajes
from comun.bitacora import Bitacora
from comun.protocolo import Enlace, serializar
from comun.vistos import RegistroVistos

_HOSTS_COMODIN = ("0.0.0.0", "", "::")


def abreviar(nombre: str) -> str:
    """'Nodo 3' -> 'N3' para que la ruta quepa en una línea."""
    m = re.fullmatch(r"[Nn]odo\s*(\d+)", nombre or "")
    return f"N{m.group(1)}" if m else (nombre or "?")


class Nodo:
    def __init__(self, puerto: int, nombre: str, host: str = "127.0.0.1", semillas=(), *,
                 bitacora: Bitacora | None = None, eventos=None):
        self.nombre = nombre
        self.host = host
        self.puerto = puerto
        self.hash = huella.de_entidad(mensajes.NODO, nombre)
        self.bitacora = bitacora or Bitacora(nombre, self.hash)
        self.eventos = eventos

        self._lock = threading.RLock()
        self.vecinos: dict[str, Enlace] = {}   # hash de nodo -> enlace
        self.celulas: dict[str, Enlace] = {}   # hash de célula -> enlace
        self._enlaces: set[Enlace] = set()     # todos, incluidos los que no se presentan aún
        self.conocidos: set[str] = set()       # endpoints de nodos
        self.alias: dict[str, str] = {}        # endpoint -> hash del nodo que atiende ahí
        self.propios: set[str] = set()         # endpoints que resultaron ser este mismo nodo
        self._marcando: set[str] = set()
        self._reintento: dict[str, tuple[float, float]] = {}  # ep -> (próximo intento, backoff)
        self._inalcanzables: set[str] = set()  # para registrar solo cambios de estado
        self._nombres: dict[str, str] = {self.hash: nombre}

        self.vistos = RegistroVistos()
        self.contadores = {"recibidos": 0, "reenviados": 0, "duplicados": 0,
                           "ttl_agotado": 0, "descartados": 0}

        self._activo = threading.Event()
        self._despertar = threading.Event()
        self._servidor: socket.socket | None = None
        self._semillas = [s for s in semillas if s]

    # ------------------------------------------------------------------ vida

    @property
    def endpoint(self) -> str:
        return mensajes.endpoint(self.host, self.puerto)

    def iniciar(self) -> None:
        """Abre el puerto y arranca los hilos. Lanza OSError si el puerto está ocupado."""
        servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: nadie más puede compartir el puerto
            servidor.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            servidor.bind((self.host, self.puerto))
            servidor.listen(64)
        except OSError:
            servidor.close()
            raise
        self._servidor = servidor
        self.puerto = servidor.getsockname()[1]  # por si se pidió el puerto 0 (pruebas)
        self.propios.add(self.endpoint)
        self._activo.set()

        semillas = []
        for s in self._semillas:
            try:
                semillas.append(mensajes.endpoint(*mensajes.separar_endpoint(s)))
            except ValueError as e:
                self._log("ERROR", f"semilla ignorada: {e}")
        with self._lock:
            self.conocidos.update(ep for ep in semillas if ep not in self.propios)

        self._log("INICIO", f"{self.nombre} · {huella.corto(self.hash)} · escucha {self.endpoint}"
                            f" · semillas: {', '.join(semillas) or 'ninguna'}")
        threading.Thread(target=self._aceptar, name="aceptador", daemon=True).start()
        threading.Thread(target=self._supervisar, name="supervisor", daemon=True).start()
        self._despertar.set()

    def detener(self) -> None:
        if not self._activo.is_set():
            return
        self._activo.clear()
        self._despertar.set()
        if self._servidor is not None:
            try:
                self._servidor.close()
            except OSError:
                pass
        with self._lock:
            enlaces = list(self._enlaces)
        for e in enlaces:
            e.cerrar("nodo detenido")
        self._log("FIN", f"{self.nombre} detenido")

    @property
    def activo(self) -> bool:
        return self._activo.is_set()

    # ------------------------------------------------------------ conexiones

    def _nuevo_enlace(self, sock: socket.socket, saliente: bool, ep: str | None) -> Enlace:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        enlace = Enlace(sock, saliente, ep, al_mensaje=self._al_mensaje,
                        al_problema=self._al_problema, al_cerrar=self._al_cerrar,
                        bitacora=self.bitacora, etiqueta="saliente" if saliente else "entrante")
        enlace.respuesta = threading.Event()  # para el marcador: llegó BIENVENIDA o RECHAZO
        enlace.rechazado = False              # el par contestó, pero el enlace sobra
        with self._lock:
            self._enlaces.add(enlace)
        return enlace

    def _aceptar(self) -> None:
        while self._activo.is_set():
            try:
                sock, _ = self._servidor.accept()
            except OSError:
                if self._activo.is_set():
                    self._log("ERROR", "accept() falló; se sigue escuchando")
                    time.sleep(0.2)
                continue
            try:
                enlace = self._nuevo_enlace(sock, saliente=False, ep=None)
                enlace.iniciar()
                t = threading.Timer(config.HOLA_TIMEOUT, self._vencer_hola, args=(enlace,))
                t.daemon = True
                t.start()
            except Exception as e:
                self._log("ERROR", f"no se pudo atender una conexión entrante: {e}")

    def _vencer_hola(self, enlace: Enlace) -> None:
        if enlace.vivo and not enlace.presentado:
            self._log("DROP", f"conexión de {enlace.ip_par} sin HOLA en "
                              f"{config.HOLA_TIMEOUT:g} s; se cierra")
            enlace.cerrar("sin HOLA")

    def _supervisar(self) -> None:
        """Cada SUPERVISOR segundos (o cuando algo cambia), marca a los
        endpoints conocidos que no tienen enlace ni marcador en curso."""
        while self._activo.is_set():
            self._despertar.wait(config.SUPERVISOR)
            self._despertar.clear()
            if not self._activo.is_set():
                return
            try:
                ahora = time.monotonic()
                with self._lock:
                    pendientes = [
                        ep for ep in sorted(self.conocidos)
                        if ep not in self.propios
                        and not self._cubierto(ep)
                        and ep not in self._marcando
                        and self._reintento.get(ep, (0.0, 0.0))[0] <= ahora
                    ]
                    self._marcando.update(pendientes)
                for ep in pendientes:
                    threading.Thread(target=self._marcar, args=(ep,), name=f"marcador-{ep}",
                                     daemon=True).start()
            except Exception as e:
                self._log("ERROR", f"supervisor: {e}")

    def _cubierto(self, ep: str) -> bool:
        h = self.alias.get(ep)
        return h is not None and (h == self.hash or h in self.vecinos)

    def _marcar(self, ep: str) -> None:
        """Un intento de conexión saliente hacia ``ep``. Si falla, agenda el
        siguiente con backoff; el supervisor lo relanza cuando toque."""
        try:
            try:
                host, puerto = mensajes.separar_endpoint(ep)
                sock = socket.create_connection((host, puerto), timeout=config.CONECTAR_TIMEOUT)
                sock.settimeout(None)
            except (OSError, ValueError) as e:
                self._fallo_marcado(ep, str(e))
                return
            enlace = self._nuevo_enlace(sock, saliente=True, ep=ep)
            enlace.enviar(mensajes.hola(mensajes.NODO, self.hash, self.nombre,
                                        escucha=self.puerto))
            enlace.iniciar()
            if not enlace.respuesta.wait(config.BIENVENIDA_TIMEOUT):
                enlace.cerrar("sin BIENVENIDA")
                self._fallo_marcado(ep, "no contestó el HOLA")
            elif enlace.presentado:
                with self._lock:
                    self._reintento.pop(ep, None)
                    self._inalcanzables.discard(ep)
            elif not enlace.rechazado:
                self._fallo_marcado(ep, enlace.motivo_cierre or "se cerró antes de la BIENVENIDA")
        except Exception as e:
            self._log("ERROR", f"marcador {ep}: {e}")
        finally:
            with self._lock:
                self._marcando.discard(ep)

    def _fallo_marcado(self, ep: str, detalle: str) -> None:
        with self._lock:
            _, backoff = self._reintento.get(ep, (0.0, 0.0))
            backoff = min(max(backoff * 2, config.BACKOFF_MIN), config.BACKOFF_MAX)
            self._reintento[ep] = (time.monotonic() + backoff, backoff)
            nuevo = ep not in self._inalcanzables
            self._inalcanzables.add(ep)
        if nuevo:  # solo el cambio de estado, no cada intento
            self._log("INALCANZABLE", f"{ep}: {detalle}; se reintenta con backoff "
                                      f"(máx. {config.BACKOFF_MAX:g} s)")

    # -------------------------------------------------------------- mensajes

    def _al_mensaje(self, enlace: Enlace, m: dict) -> None:
        ctrl = m.get("ctrl")
        if not enlace.presentado:
            if not enlace.saliente and ctrl == mensajes.HOLA:
                self._registrar_entrante(enlace, m)
            elif enlace.saliente and ctrl == mensajes.BIENVENIDA:
                self._registrar_saliente(enlace, m)
            elif enlace.saliente and ctrl == mensajes.RECHAZO:
                self._rechazado(enlace, m)
            else:
                self._descartar(enlace, "datos antes de presentarse")
            return
        if ctrl is not None:
            if ctrl == mensajes.PARES and enlace.entidad == mensajes.NODO:
                self._aprender(mensajes.endpoints_validos(m.get("nodos")))
            elif ctrl == mensajes.RECHAZO and m.get("motivo") == mensajes.DUPLICADO:
                enlace.cerrar(f"duplicado: {enlace.nombre} conserva el otro enlace")
            else:
                self._descartar(enlace, f"control inesperado {ctrl!r}")
            return
        self._difundir(enlace, m)

    def _al_problema(self, enlace: Enlace, problema: str) -> None:
        self._descartar(enlace, problema)

    def _descartar(self, enlace: Enlace, motivo: str) -> None:
        with self._lock:
            self.contadores["descartados"] += 1
        de = enlace.nombre or enlace.ip_par or "?"
        self._log("DROP", f"de {de}: {motivo}", evento="DROP", de=de, detalle=motivo)

    def _al_cerrar(self, enlace: Enlace, motivo: str | None) -> None:
        enlace.respuesta.set()
        quitado = None
        with self._lock:
            self._enlaces.discard(enlace)
            if enlace.presentado:
                tabla = self.vecinos if enlace.entidad == mensajes.NODO else self.celulas
                if tabla.get(enlace.hash) is enlace:
                    del tabla[enlace.hash]
                    quitado = "vecino" if tabla is self.vecinos else "célula"
        if quitado is None:
            return  # nunca se presentó, o era un enlace duplicado ya reemplazado
        motivo = motivo or ""
        if motivo.startswith("LENTO"):
            evento = "LENTO"
        elif motivo.startswith("duplicado"):
            evento = "DUPLICADO"  # resolución de la regla de enlace duplicado, no una caída
        else:
            evento = "DESCONEXION"
        self._log(evento, f"{quitado} {enlace.nombre} ({huella.corto(enlace.hash)}): {motivo}",
                  evento=evento, de=enlace.nombre)
        self._tablas_cambiaron()
        if quitado == "vecino":
            self._despertar.set()  # que el supervisor intente recuperarlo

    # ---------------------------------------------------------- presentación

    def _anunciables(self) -> list[str]:
        """Endpoints de nodos que se comparten por BIENVENIDA y PARES."""
        eps = set(self.conocidos)
        if self.host not in _HOSTS_COMODIN:
            eps.add(self.endpoint)
        return sorted(eps)

    def _rechazar(self, enlace: Enlace, motivo: str, detalle: str) -> None:
        enlace.enviar(mensajes.rechazo(motivo, self.hash))
        enlace.cerrar(f"RECHAZO {motivo}", vaciar=True)
        self._log("RECHAZO", f"{detalle} → RECHAZO({motivo})")

    def _registrar_entrante(self, enlace: Enlace, hola: dict) -> None:
        problema = mensajes.validar_hola(hola)
        if problema:
            self._rechazar(enlace, problema[0], f"HOLA de {enlace.ip_par}: {problema[1]}")
            return
        h, nombre, entidad = hola["hash"], hola["nombre"], hola["entidad"]
        if h == self.hash:
            self._rechazar(enlace, mensajes.AUTOCONEXION, "me marqué a mí mismo")
            return

        if entidad == mensajes.NODO:
            ep = mensajes.endpoint(enlace.ip_par, hola["escucha"])
            enlace.endpoint = ep
            with self._lock:
                self.alias[ep] = h
                self._nombres[h] = nombre
                crecio = self._agregar_conocidos([ep])
                aceptado = self._registrar_vecino(enlace, h, nombre, dar_bienvenida=True)
            if not aceptado:
                self._rechazar(enlace, mensajes.DUPLICADO,
                               f"{nombre} ya tiene enlace conmigo (llegó otro entrante)")
            else:
                self._log("CONEXION", f"vecino {nombre} ({huella.corto(h)}) desde {ep} · entrante",
                          evento="CONEXION", de=nombre)
                self._tablas_cambiaron()
            if crecio:
                self._difundir_pares()
            return

        with self._lock:
            viejo = self.celulas.get(h)
            self._identificar(enlace, entidad, h, nombre, hola.get("servicio"))
            enlace.endpoint = mensajes.endpoint(enlace.ip_par, enlace.puerto_par)
            enlace.enviar(mensajes.bienvenida(self.hash, self.nombre, self._anunciables()))
            self.celulas[h] = enlace
        if viejo is not None and viejo is not enlace:
            viejo.cerrar("reemplazado: la célula se reconectó")
        servicio = f" {hola['servicio']}" if hola.get("servicio") else ""
        self._log("CONEXION", f"célula {entidad}{servicio} {nombre} ({huella.corto(h)})",
                  evento="CONEXION", de=nombre)
        self._tablas_cambiaron()

    def _registrar_saliente(self, enlace: Enlace, bienvenida: dict) -> None:
        h, nombre = bienvenida.get("hash"), bienvenida.get("nombre")
        if not mensajes.es_hash(h) or not isinstance(nombre, str):
            enlace.cerrar("BIENVENIDA inválida")
            enlace.respuesta.set()
            return
        with self._lock:
            self.alias[enlace.endpoint] = h
            self._nombres[h] = nombre
            aceptado = self._registrar_vecino(enlace, h, nombre, dar_bienvenida=False)
        if aceptado:
            self._log("CONEXION", f"vecino {nombre} ({huella.corto(h)}) en {enlace.endpoint}"
                                  f" · saliente", evento="CONEXION", de=nombre)
            self._tablas_cambiaron()
        else:
            enlace.rechazado = True
            # El par ya registró este enlace (lo aceptó al recibir mi HOLA). Se le
            # avisa, para que lo cierre como DUPLICADO y no lo tome por una caída.
            enlace.enviar(mensajes.rechazo(mensajes.DUPLICADO, self.hash))
            enlace.cerrar("duplicado: ya había enlace con ese nodo", vaciar=True)
            self._log("RECHAZO", f"enlace saliente a {nombre} sobra (ya hay uno); se cierra")
        enlace.respuesta.set()
        self._aprender(mensajes.endpoints_validos(bienvenida.get("nodos")))

    def _rechazado(self, enlace: Enlace, rechazo: dict) -> None:
        motivo, h = rechazo.get("motivo"), rechazo.get("hash")
        ep = enlace.endpoint
        enlace.rechazado = True
        with self._lock:
            if motivo == mensajes.AUTOCONEXION:
                self.propios.add(ep)
            elif mensajes.es_hash(h):
                self.alias[ep] = h
            # Si el enlace que sí sirve se cae después, el supervisor reintenta.
            self._reintento[ep] = (time.monotonic() + config.BACKOFF_MIN, config.BACKOFF_MIN)
            self._inalcanzables.discard(ep)
        self._log("RECHAZO", f"{ep} me rechazó: {motivo}")
        enlace.cerrar(f"rechazado: {motivo}")
        enlace.respuesta.set()

    def _identificar(self, enlace: Enlace, entidad, h, nombre, servicio=None) -> None:
        enlace.entidad, enlace.hash, enlace.nombre, enlace.servicio = entidad, h, nombre, servicio
        enlace.presentado = True

    def _registrar_vecino(self, enlace: Enlace, h: str, nombre: str, *,
                          dar_bienvenida: bool) -> bool:
        """Regla de enlace duplicado (con el lock tomado).

        Sea ``preferido = min(mi_hash, hash_par)``, el nodo que "debe" iniciar.
        Si ya hay un enlace con ese nodo, se queda el NUEVO solo si lo inició el
        preferido y el existente no; en cualquier otro caso se queda el
        existente. La regla depende solo de los hashes y de quién inició cada
        enlace, así que ambos lados llegan a la misma decisión.
        """
        existente = self.vecinos.get(h)
        if existente is not None and existente is not enlace and existente.vivo:
            preferido = min(self.hash, h)

            def iniciador(e: Enlace) -> str:
                return self.hash if e.saliente else h

            if iniciador(enlace) == preferido and iniciador(existente) != preferido:
                # Se avisa al par para que registre el cierre como DUPLICADO y no
                # como una caída.
                existente.enviar(mensajes.rechazo(mensajes.DUPLICADO, self.hash))
                existente.cerrar("duplicado: se conserva el enlace iniciado por el preferido",
                                 vaciar=True)
                # El viejo sale de la tabla sin pasar por _al_cerrar (ya no es el
                # registrado): se anota aquí para que la segunda CONEXION se entienda.
                self._log("DUPLICADO", f"{nombre}: dos enlaces; se conserva el iniciado por "
                                       f"el preferido y se cierra el otro",
                          evento="DUPLICADO", de=nombre)
            else:
                return False
        self._identificar(enlace, mensajes.NODO, h, nombre)
        if dar_bienvenida:
            # Se encola ANTES de publicar el enlace en la tabla: así la
            # BIENVENIDA es lo primero que recibe, antes que cualquier dato.
            enlace.enviar(mensajes.bienvenida(self.hash, self.nombre, self._anunciables()))
        self.vecinos[h] = enlace
        # Volvió (por donde sea): si cae otra vez, ese cambio se registra de nuevo.
        self._inalcanzables.discard(enlace.endpoint)
        self._reintento.pop(enlace.endpoint, None)
        return True

    # --------------------------------------------------------------- gossip

    def _agregar_conocidos(self, eps) -> bool:
        """Con el lock tomado. True si el conjunto creció."""
        nuevos = [ep for ep in eps if ep not in self.conocidos and ep not in self.propios]
        self.conocidos.update(nuevos)
        return bool(nuevos)

    def _aprender(self, eps: list[str]) -> None:
        with self._lock:
            crecio = self._agregar_conocidos(eps)
        if crecio:
            self._difundir_pares()

    def _difundir_pares(self) -> None:
        """PARES a todos los enlaces presentados (nodos y células). Converge
        porque solo se manda cuando el conjunto crece, y es finito."""
        with self._lock:
            datos = serializar(mensajes.pares(self._anunciables()))
            destinos = list(self.vecinos.values()) + list(self.celulas.values())
            total = len(self.conocidos)
        for e in destinos:
            e.enviar_bytes(datos)
        self._log("PARES", f"conozco {total} nodo(s) además de mí; aviso a {len(destinos)} enlace(s)")
        self._despertar.set()

    # ------------------------------------------------------------ broadcast

    def _difundir(self, enlace: Enlace, m: dict) -> None:
        """Inundación con las defensas contra ciclos (§9, §11):

        1. id único + registro temporal: un id ya visto es DUP y no se reenvía;
        2. TTL: cuántos nodos más pueden procesarlo;
        3. horizonte dividido + ruta: nunca de vuelta al enlace de entrada ni a
           nodos que ya lo procesaron.
        """
        with self._lock:
            self.contadores["recibidos"] += 1
        motivo = mensajes.validar_datos(m)
        if motivo:
            self._descartar(enlace, motivo)
            return

        codigo, id8 = m["codigo"], huella.corto(m["id"])
        origen = m.get("nombre_origen") or huella.corto(m["origen"])
        silencioso = codigo in config.CODIGOS_SILENCIOSOS
        campos = {"codigo": codigo, "id8": id8, "origen": origen, "de": enlace.nombre}

        if not self.vistos.marcar_si_nuevo(m["id"]):
            with self._lock:
                self.contadores["duplicados"] += 1
            self._log("DUP", f"{codigo} #{id8} de {enlace.nombre}: ya procesado; no se "
                             f"retransmite", consola=not silencioso, evento="DUP",
                      ruta=self._ruta_legible(m["ruta"]), **campos)
            return

        ttl = min(m["ttl"], config.TTL_MAX)
        if ttl <= 0:
            with self._lock:
                self.contadores["ttl_agotado"] += 1
            self._log("TTL", f"{codigo} #{id8} llegó con ttl={m['ttl']}; no se procesa",
                      consola=not silencioso, evento="TTL",
                      ruta=self._ruta_legible(m["ruta"]), **campos)
            return

        m["ttl"] = ttl - 1
        m["ruta"].append(self.hash)
        datos = serializar(m)  # una sola vez para todos los destinos
        with self._lock:
            celulas = [e for e in self.celulas.values() if e is not enlace]
            nodos = [] if m["ttl"] <= 0 else [
                e for h, e in self.vecinos.items() if e is not enlace and h not in m["ruta"]]
            self.contadores["reenviados"] += 1
            if m["ttl"] <= 0:
                self.contadores["ttl_agotado"] += 1
        for e in celulas + nodos:
            e.enviar_bytes(datos)

        ruta = self._ruta_legible(m["ruta"])
        destinos = f"{len(nodos)} nodo(s) / {len(celulas)} célula(s)"
        self._log("FWD", f"{codigo} #{id8} origen={origen} de={enlace.nombre} ruta={ruta} "
                         f"ttl={m['ttl']} → {destinos}", consola=not silencioso,
                  evento="FWD", ruta=ruta, destinos=destinos, **campos)
        if m["ttl"] <= 0:
            self._log("TTL", f"{codigo} #{id8}: ttl agotado aquí; se entregó a mis células "
                             f"pero no se reenvía a nodos", consola=not silencioso,
                      evento="TTL", ruta=ruta, **campos)

    def _ruta_legible(self, ruta: list[str]) -> str:
        with self._lock:
            return "→".join(abreviar(self._nombres.get(h, huella.corto(h))) for h in ruta)

    # ---------------------------------------------------------- observación

    def instantanea(self) -> dict:
        """Copia del estado para la ventana o las pruebas."""
        with self._lock:
            def fila(e: Enlace) -> dict:
                return {"hash": e.hash, "nombre": e.nombre, "entidad": e.entidad,
                        "servicio": e.servicio, "endpoint": e.endpoint,
                        "sentido": "saliente" if e.saliente else "entrante", "desde": e.desde}
            return {
                "vecinos": [fila(e) for e in self.vecinos.values()],
                "celulas": [fila(e) for e in self.celulas.values()],
                "contadores": dict(self.contadores),
                "vistos": len(self.vistos),
                "conocidos": sorted(self.conocidos),
            }

    def _tablas_cambiaron(self) -> None:
        if self.eventos is not None:
            self.eventos.put(("tablas", None))

    def _log(self, tipo: str, texto: str, *, consola: bool = True, **campos) -> None:
        """Bitácora y, si hay ``campos``, una fila de tráfico para la ventana."""
        self.bitacora(tipo, texto, consola=consola)
        if self.eventos is not None and campos:
            campos.setdefault("evento", tipo)
            campos["hora"] = time.strftime("%H:%M:%S")
            self.eventos.put(("trafico", campos))
