"""Célula servidor (el ASM de ADS): atiende UN servicio por instancia.

Flujo de una ronda ``(id_operacion, intento)`` en cada servidor del servicio:

1. **RX X_REQ** → publica ``X_ACK`` de inmediato (en el hilo lector, antes de
   encolar; el retardo artificial nunca lo atrasa), se anota como acusadora y
   encola. Las rondas anteriores de la misma operación quedan **superadas**; y
   si el REQ llega cuando ya se conoce un intento posterior (desorden en la
   malla), es la propia ronda la que queda superada: ni acusa ni se encola.
2. **RX X_ACK** de otra célula → la suma a ``acusadores``. Si la ronda aún no
   existe, crea un **esqueleto**: el acuse puede llegar antes que el REQ porque
   viajan por caminos distintos de la malla.
3. **RX X_RES** de la ronda k → marca **resueltas** las rondas con intento ≤ k.
   Las posteriores no: un reintento significa que la GUI no recibió esa
   respuesta.
4. **Trabajador**: espera ``VENTANA_ELECCION`` desde que recibió el REQ, ordena
   a los acusadores con ``huella.ranking`` (HRW) y ve su posición r:
   r == 0 → TITULAR (calcula y responde); r > 0 → RESPALDO escalonado: si a los
   ``r·RELEVO`` segundos nadie respondió, hace el RELEVO. Antes de publicar se
   revisa otra vez el estado: si ya hubo respuesta, la suya se SUPRIME.

Todos calculan el mismo ranking sobre el mismo conjunto, así que hay una sola
respuesta sin coordinador ni mensajes extra. Además emite ``SRV_LAT`` al
conectarse y cada ``LATIDO`` segundos.
"""

import heapq
import itertools
import queue
import threading
import time
from dataclasses import dataclass, field

from celula.base import Celula
from comun import codigos, config, formato, huella, mensajes
from comun.bitacora import Bitacora
from servidor import calculo

# Estados de una ronda.
ESQUELETO = "esqueleto"   # solo se conocen acuses; el REQ no ha llegado
EN_COLA = "en_cola"
TITULAR = "titular"
RESPALDO = "respaldo"
RESUELTA = "resuelta"
SUPERADA = "superada"
_TERMINADAS = (RESUELTA, SUPERADA)


@dataclass
class Ronda:
    id_operacion: str
    intento: int
    creada: float = field(default_factory=time.monotonic)
    estado: str = ESQUELETO
    tiene_req: bool = False
    a: object = None
    b: object = None
    id_solicitud: str | None = None
    t_rx: float | None = None
    gui: str = "?"
    acusadores: set = field(default_factory=set)
    nombres: dict = field(default_factory=dict)  # hash de célula -> nombre (solo para mostrar)


def _op8(ronda: Ronda) -> str:
    return f"op {huella.corto(ronda.id_operacion)} · intento {ronda.intento}"


class Programador:
    """Ejecuta funciones a una hora (monotónica) dada, en un solo hilo.

    Lo usan los respaldos: "si a esta hora nadie respondió, hago el relevo".
    """

    def __init__(self, al_error):
        self._heap: list = []
        self._cond = threading.Condition()
        self._seq = itertools.count()
        self._activo = True
        self._al_error = al_error
        threading.Thread(target=self._correr, name="programador", daemon=True).start()

    def agendar(self, cuando: float, funcion) -> None:
        with self._cond:
            heapq.heappush(self._heap, (cuando, next(self._seq), funcion))
            self._cond.notify()

    def detener(self) -> None:
        with self._cond:
            self._activo = False
            self._cond.notify()

    def _correr(self) -> None:
        while True:
            with self._cond:
                while self._activo:
                    if self._heap and self._heap[0][0] <= time.monotonic():
                        break
                    espera = self._heap[0][0] - time.monotonic() if self._heap else None
                    self._cond.wait(espera)
                if not self._activo:
                    return
                _, _, funcion = heapq.heappop(self._heap)
            try:
                funcion()
            except Exception as e:
                self._al_error(e)


class Servidor(Celula):
    def __init__(self, servicio: str, nombre: str, nodo: str, *, retardo_ms: int = 0,
                 bitacora: Bitacora | None = None, eventos=None):
        if servicio not in codigos.SERVICIOS:
            raise ValueError(f"servicio desconocido: {servicio!r}")
        super().__init__(mensajes.SERVIDOR, nombre, nodo, servicio,
                         bitacora=bitacora, eventos=eventos)
        self.retardo_ms = max(0, int(retardo_ms))
        self.cod_req = codigos.codigo(servicio, codigos.REQ)
        self.cod_ack = codigos.codigo(servicio, codigos.ACK)
        self.cod_res = codigos.codigo(servicio, codigos.RES)

        self._lock_rondas = threading.RLock()
        self.rondas: dict[tuple[str, int], Ronda] = {}
        self._resueltas: dict[str, tuple[int, float]] = {}  # id_operacion -> (máx. k resuelto, t)
        self._cola: queue.Queue = queue.Queue()
        self.atendidas = 0
        self.ignorados = 0
        self.latidos_vistos = 0
        self._programador: Programador | None = None

    # ------------------------------------------------------------------ vida

    def iniciar(self) -> None:
        self._programador = Programador(lambda e: self.log("ERROR", f"programador: {e!r}"))
        threading.Thread(target=self._trabajar, name=f"{self.nombre}-trabajador",
                         daemon=True).start()
        threading.Thread(target=self._latir_siempre, name=f"{self.nombre}-latido",
                         daemon=True).start()
        super().iniciar()
        if self.retardo_ms:
            self.log("INICIO", f"retardo artificial de {self.retardo_ms} ms al calcular "
                               f"(el acuse no se retrasa)")

    def detener(self) -> None:
        super().detener()
        if self._programador:
            self._programador.detener()
        self._cola.put(None)

    def al_conectar(self, nodo: dict, como: str) -> None:
        self._latir()  # presentación inmediata: las GUIs lo ven vivo al instante

    # -------------------------------------------------------------- latidos

    def _latir(self) -> None:
        nodo = self.nodo_actual or {}
        self.publicar(codigos.SRV_LAT, {
            "servicio": self.servicio, "en_cola": self._cola.qsize(),
            "atendidas": self.atendidas, "nodo": nodo.get("hash"),
            "nodo_nombre": nodo.get("nombre"),
        })

    def _latir_siempre(self) -> None:
        while not self._parar.wait(config.LATIDO):
            try:
                if self.conectado:
                    self._latir()
                self._purgar()
            except Exception as e:
                self.log("ERROR", f"latido: {e!r}")

    def _purgar(self) -> None:
        limite = time.monotonic() - config.RONDAS_VIGENCIA
        with self._lock_rondas:
            for clave in [c for c, r in self.rondas.items() if r.creada < limite]:
                del self.rondas[clave]
            for op in [o for o, (_, t) in self._resueltas.items() if t < limite]:
                del self._resueltas[op]

    # ------------------------------------------------------------ recepción

    def procesar(self, m: dict) -> None:
        codigo = m["codigo"]
        if codigo == self.cod_req:
            self._rx_req(m)
        elif codigo == self.cod_ack:
            self._rx_ack(m)
        elif codigo == self.cod_res:
            self._rx_res(m)
        elif codigo == codigos.SRV_LAT:
            self.latidos_vistos += 1  # se ignoran sin registrarlos: serían puro ruido
        else:
            self.ignorados += 1
            self.log("IGNORA", f"{codigo} de {m.get('nombre_origen')} "
                               f"({huella.corto(m['id'])}): no es de {self.servicio}",
                     consola=False)

    def _clave(self, m: dict) -> tuple[str, int] | None:
        cuerpo = m["cuerpo"]
        op, intento = cuerpo.get("id_operacion"), cuerpo.get("intento")
        if (not mensajes.es_hash(op) or not isinstance(intento, int)
                or isinstance(intento, bool) or intento < 1):
            self.log("DROP", f"{m['codigo']} {huella.corto(m['id'])} con cuerpo inválido")
            return None
        return op, intento

    def _ronda(self, clave: tuple[str, int]) -> Ronda:
        """La ronda de la clave; la crea (esqueleto) si no existe. Con el lock tomado."""
        ronda = self.rondas.get(clave)
        if ronda is None:
            ronda = Ronda(*clave)
            k, _ = self._resueltas.get(clave[0], (0, 0))
            if clave[1] <= k:
                ronda.estado = RESUELTA  # ya se respondió esta ronda (o una posterior)
            self.rondas[clave] = ronda
        return ronda

    def _rx_req(self, m: dict) -> None:
        clave = self._clave(m)
        if clave is None:
            return
        cuerpo = m["cuerpo"]
        with self._lock_rondas:
            ronda = self._ronda(clave)
            if ronda.tiene_req:
                repetido = True
            else:
                repetido = False
                ronda.tiene_req = True
                ronda.a, ronda.b = cuerpo.get("a"), cuerpo.get("b")
                ronda.id_solicitud = m["id"]
                ronda.t_rx = time.monotonic()
                ronda.gui = m.get("nombre_origen") or "?"
                ronda.acusadores.add(self.hash)
                ronda.nombres[self.hash] = self.nombre
                if ronda.estado == ESQUELETO:
                    ronda.estado = EN_COLA
                # Desorden en la malla: si ya conozco un intento posterior, este REQ
                # llegó tarde. La GUI ya no lo espera; responderlo sería un RES de más.
                posterior = max((k for op, k in self.rondas
                                 if op == clave[0] and k > clave[1]), default=0)
                if posterior and ronda.estado not in _TERMINADAS:
                    ronda.estado = SUPERADA
                superadas = []
                for (op, k), vieja in self.rondas.items():
                    if op == clave[0] and k < clave[1] and vieja.estado not in _TERMINADAS:
                        vieja.estado = SUPERADA
                        superadas.append(k)
        if repetido:
            self.log("RX", f"{self.cod_req} {_op8(ronda)} repetido; ya estaba en mi cola")
            return

        texto = formato.operacion(ronda.a, self.servicio, ronda.b)
        self.log("RX", f"{self.cod_req} {_op8(ronda)} de {ronda.gui}: {texto} "
                       f"(solicitud {huella.corto(ronda.id_solicitud)})")
        if posterior and ronda.estado == SUPERADA:
            self.log("SUPERADA", f"{_op8(ronda)} llegó después del intento {posterior}; "
                                 f"no se acusa ni se encola")
            return
        # Acuse INMEDIATO, antes de encolar: prueba de recepción, no de cálculo.
        en_cola = self._cola.qsize()
        ack = self.publicar(self.cod_ack, {"id_operacion": clave[0],
                                           "id_solicitud": ronda.id_solicitud,
                                           "intento": clave[1], "en_cola": en_cola})
        if ack is not None:
            self.log("ACUSE", f"{self.cod_ack} {_op8(ronda)} → {ronda.gui} "
                              f"(acuse {huella.corto(ack['id'])})")
        for k in superadas:
            self.log("SUPERADA", f"op {huella.corto(clave[0])} · intento {k}: la GUI ya va en "
                                 f"el intento {clave[1]}")
        self._cola.put(("eleccion", clave))
        self.log("COLA", f"{_op8(ronda)} encolada ({en_cola} antes en espera)")

    def _rx_ack(self, m: dict) -> None:
        clave = self._clave(m)
        if clave is None:
            return
        with self._lock_rondas:
            ronda = self._ronda(clave)
            ronda.acusadores.add(m["origen"])
            ronda.nombres[m["origen"]] = m.get("nombre_origen") or huella.corto(m["origen"])
            esqueleto = not ronda.tiene_req
            n = len(ronda.acusadores)
        nota = " (aún sin REQ: ronda esqueleto)" if esqueleto else ""
        self.log("RX", f"{self.cod_ack} {_op8(ronda)} de {m.get('nombre_origen')} "
                       f"→ {n} acusador(es){nota}")

    def _rx_res(self, m: dict) -> None:
        clave = self._clave(m)
        if clave is None:
            return
        cuerpo = m["cuerpo"]
        n = self._marcar_resueltas(*clave)
        self.log("RX", f"{self.cod_res} op {huella.corto(clave[0])} · intento {clave[1]} "
                       f"de {m.get('nombre_origen')} ({cuerpo.get('rol')}); "
                       f"{n} ronda(s) mía(s) quedan resueltas")

    def _marcar_resueltas(self, op: str, k: int) -> int:
        """Una respuesta a la ronda k resuelve las rondas ≤ k, nunca las posteriores."""
        n = 0
        with self._lock_rondas:
            previo, _ = self._resueltas.get(op, (0, 0))
            self._resueltas[op] = (max(previo, k), time.monotonic())
            for (o, i), ronda in self.rondas.items():
                if o == op and i <= k and ronda.estado != RESUELTA:
                    ronda.estado = RESUELTA
                    n += 1
        return n

    # ------------------------------------------------------------ trabajador

    def _trabajar(self) -> None:
        while True:
            item = self._cola.get()
            if item is None:
                return
            try:
                if item[0] == "eleccion":
                    self._elegir(item[1])
                else:
                    _, clave, r = item
                    self._ejecutar(clave, f"relevo {r}")
            except Exception as e:
                self.log("ERROR", f"trabajador: {e!r}")

    def _elegir(self, clave: tuple[str, int]) -> None:
        with self._lock_rondas:
            ronda = self.rondas.get(clave)
            if ronda is None:
                return
            t_rx = ronda.t_rx
        espera = t_rx + config.VENTANA_ELECCION - time.monotonic()
        if espera > 0 and self._parar.wait(espera):
            return

        with self._lock_rondas:
            if ronda.estado in _TERMINADAS:
                estado, r = ronda.estado, None
            else:
                orden = huella.ranking(ronda.acusadores, clave[0], clave[1])
                r = orden.index(self.hash)
                ronda.estado = TITULAR if r == 0 else RESPALDO
                titular = ronda.nombres.get(orden[0], huella.corto(orden[0]))
                lista = ", ".join(ronda.nombres.get(h, huella.corto(h)) for h in orden)
        if r is None:
            self.log("RETIRADA", f"{_op8(ronda)} ya está {estado}; no participo")
            return
        if r == 0:
            self.log("TITULAR", f"{_op8(ronda)} · rank 0 de {len(orden)} [{lista}]")
            self._ejecutar(clave, "titular")
            return
        plazo = t_rx + config.VENTANA_ELECCION + r * config.RELEVO
        self.log("RESPALDO", f"{_op8(ronda)} · rank {r} de {len(orden)} [{lista}]; titular "
                             f"{titular}; relevo si nadie responde en {r * config.RELEVO:.1f} s")
        self._programador.agendar(plazo, lambda: self._revisar_respaldo(clave, r))

    def _revisar_respaldo(self, clave: tuple[str, int], r: int) -> None:
        with self._lock_rondas:
            ronda = self.rondas.get(clave)
            if ronda is None:
                return
            terminada = ronda.estado in _TERMINADAS
            estado = ronda.estado
        if terminada:
            self.log("LIBERADO", f"{_op8(ronda)} ya está {estado}; respaldo {r} liberado")
            return
        self.log("RELEVO", f"{_op8(ronda)}: nadie respondió; tomo el relevo {r}")
        self._cola.put(("relevo", clave, r))

    def _ejecutar(self, clave: tuple[str, int], rol: str) -> None:
        with self._lock_rondas:
            ronda = self.rondas.get(clave)
        if ronda is None:
            return
        if self.retardo_ms and self._parar.wait(self.retardo_ms / 1000):
            return
        resultado, error = calculo.calcular(self.servicio, ronda.a, ronda.b)

        # Doble revisión: mientras calculaba pudo llegar otra respuesta o un reintento.
        with self._lock_rondas:
            estado = ronda.estado
            suprimir = estado in _TERMINADAS
        if suprimir:
            self.log("SUPRIMIDA", f"{_op8(ronda)} ya está {estado}; no envío mi respuesta "
                                  f"({rol})")
            return
        self._marcar_resueltas(*clave)
        ms = round((time.monotonic() - ronda.t_rx) * 1000)
        res = self.publicar(self.cod_res, {
            "id_operacion": clave[0], "id_solicitud": ronda.id_solicitud,
            "intento": clave[1], "resultado": resultado, "error": error,
            "rol": rol, "ms": ms,
        })
        if res is None:
            return  # ya se registró como PERDIDO; la GUI reintentará
        self.atendidas += 1
        texto = formato.operacion(ronda.a, self.servicio, ronda.b, resultado, error)
        self.log("RES", f"{self.cod_res} {_op8(ronda)} · {texto} · {rol} · solicitud "
                        f"{huella.corto(ronda.id_solicitud)} ↔ respuesta "
                        f"{huella.corto(res['id'])} · {ms} ms")
