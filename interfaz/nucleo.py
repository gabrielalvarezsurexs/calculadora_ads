"""Célula GUI, sin Tkinter: solicita, cuenta acuses, reintenta y decide qué
operadores están disponibles. La ventana (``interfaz/gui.py``) solo muestra lo
que este módulo empuja a ``eventos``.

Reglas (plan §5.1 y §5.3):

* La operación se **registra antes de publicar**: un acuse muy rápido podría
  llegar antes de que exista. Hay una sola operación en vuelo a la vez.
* **Quórum por intento**: cada ``X_ACK`` mío suma su origen al conjunto de SU
  intento. No se acumula entre intentos, porque una célula que acusó el intento
  1 y luego murió ya no tiene la operación.
* El ``X_RES`` se acepta **solo con quórum**; si llega antes, se retiene.
* Plazos (reloj de 100 ms): sin quórum a ``VENTANA_ACUSES`` → reintento; con
  quórum pero sin resultado, plazo dinámico según el número de acusadores.
  Agotados los intentos → FALLIDA.
* Respuestas de más: para una operación RESUELTA → DUPLICADA; para una FALLIDA
  → TARDÍA. Ambas se descartan.
* **Disponibilidad por latidos**: ``SRV_LAT`` (y cada ``X_ACK``) prueba que una
  célula vive. Si las vivas de un servicio son menos que su mínimo de acuses,
  el operador se deshabilita.
* Esta GUI ignora los REQ (así no ve las solicitudes de otras GUIs) y los
  ACK/RES de operaciones ajenas; esos van a la bitácora técnica como IGNORA.

Eventos que empuja a ``eventos`` (tuplas ``(tipo, datos)``):
``("log", (hora, evento, texto))`` para el mini log, ``("operacion", fila)``,
``("disponibilidad", dict)`` y ``("conexion", dict)``.
"""

import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from celula.base import FAILOVER, Celula
from comun import codigos, config, formato, huella, mensajes
from comun.bitacora import Bitacora, hora

EN_VUELO = "en vuelo"
RESUELTA = "resuelta"
FALLIDA = "fallida"

HISTORIAL = 200        # operaciones propias que se recuerdan para clasificar respuestas tardías
MINIMO_RANGO = (1, 16)


@dataclass
class Operacion:
    id: str
    servicio: str
    a: float
    b: float
    t0: float = field(default_factory=time.monotonic)
    intento: int = 1
    enviado_en: float = field(default_factory=time.monotonic)
    acusadores: dict = field(default_factory=dict)    # intento -> set(hash de célula)
    nombres: dict = field(default_factory=dict)       # hash -> nombre (para mostrar)
    solicitudes: dict = field(default_factory=dict)   # intento -> id del REQ
    t_quorum: float | None = None
    retenido: dict | None = None                      # RES que llegó antes del quórum
    estado: str = EN_VUELO
    resultado: float | None = None
    error: str | None = None
    rol: str | None = None
    respondio: str | None = None
    id_solicitud: str | None = None                   # el REQ que atendió quien respondió
    id_respuesta: str | None = None
    ms: int | None = None
    motivo: str | None = None                         # por qué falló

    def acuses(self) -> int:
        return len(self.acusadores.get(self.intento, ()))


def _es_numero(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


class Interfaz(Celula):
    def __init__(self, nombre: str, nodo: str, *, acuses_min: int | None = None,
                 bitacora: Bitacora | None = None, eventos=None):
        super().__init__(mensajes.INTERFAZ, nombre, nodo, None,
                         bitacora=bitacora, eventos=eventos)
        minimo = acuses_min if acuses_min is not None else config.ACUSES_MIN_DEFECTO
        minimo = max(MINIMO_RANGO[0], min(MINIMO_RANGO[1], int(minimo)))
        self._lock_ops = threading.RLock()
        self.acuses_min = {s: minimo for s in codigos.SERVICIOS}
        self.operaciones: OrderedDict[str, Operacion] = OrderedDict()
        self.en_vuelo: str | None = None
        # servicio -> {hash de célula: [último visto, nombre, nombre de su nodo]}
        self.vivas: dict[str, dict[str, list]] = {s: {} for s in codigos.SERVICIOS}
        self.habilitadas = {s: False for s in codigos.SERVICIOS}
        self.ignorados = 0
        self._ultima_disp = None
        self._sin_enlace = False  # entre perder el nodo y terminar el failover

    # ------------------------------------------------------------------ vida

    def iniciar(self) -> None:
        super().iniciar()
        self._mini("ESPERANDO", "operadores deshabilitados: esperando latidos…")
        self._emitir_disponibilidad(forzar=True)
        threading.Thread(target=self._vigilar, name=f"{self.nombre}-reloj", daemon=True).start()

    def al_conectar(self, nodo: dict, como: str) -> None:
        # Mientras estuve sin enlace no podía oír latidos: eso no prueba que nadie
        # haya muerto. Les doy un plazo completo desde ahora; las muertas de verdad
        # caducan después de LATIDO_CADUCIDAD.
        with self._lock_ops:
            ahora = time.monotonic()
            for celulas in self.vivas.values():
                for datos in celulas.values():
                    datos[0] = max(datos[0], ahora)
            self._sin_enlace = False
        if como == FAILOVER:
            self._mini("FAILOVER", f"→ {nodo['nombre']} ({nodo['endpoint']})", registrar=False)
        else:
            self._mini("CONEXION", f"conectada a {nodo['nombre']} ({nodo['endpoint']})",
                       registrar=False)

    def al_desconectar(self, motivo: str | None) -> None:
        with self._lock_ops:
            self._sin_enlace = True
        self._mini("DESCONEXION", f"se perdió el nodo ({motivo or 'sin motivo'}); buscando otro…",
                   registrar=False)

    # ------------------------------------------------------------ API (GUI)

    def solicitar(self, servicio: str, a, b) -> tuple[str | None, str]:
        """Publica ``X_REQ``. Devuelve (id_operacion, texto) o (None, motivo)."""
        if servicio not in codigos.SERVICIOS:
            return None, f"servicio desconocido: {servicio!r}"
        if not (_es_numero(a) and _es_numero(b)):
            return None, "los operandos deben ser números finitos"
        cod = codigos.codigo(servicio, codigos.REQ)
        with self._lock_ops:
            if self.en_vuelo is not None:
                return None, "ya hay una operación en vuelo"
            if not self.conectado:
                return None, "sin conexión al Campo de Datos"
            self._caducar(time.monotonic())
            self._evaluar()
            if not self.habilitadas[servicio]:
                n, m = len(self.vivas[servicio]), self.acuses_min[servicio]
                texto = f"{servicio} no disponible: {n} viva(s) < {m} mínima(s)"
                self._mini("NO_DISPONIBLE", texto)
                return None, texto
            op = Operacion(huella.de_operacion(self.hash, servicio, a, b), servicio, a, b)
            self.operaciones[op.id] = op  # registrar ANTES de publicar
            self.en_vuelo = op.id
            self._recortar_historial()
            req = self.publicar(cod, {"id_operacion": op.id, "intento": 1, "a": a, "b": b})
            op.solicitudes[1] = req["id"] if req else None
        self._mini("SOLICITUD", f"{cod} {formato.operacion(a, servicio, b)} · op "
                                f"{huella.corto(op.id)} · solicitud "
                                f"{huella.corto(op.solicitudes[1]) or 'perdida'}")
        self._emitir_operacion(op)
        return op.id, "enviada"

    def ajustar_minimo(self, servicio: str, minimo: int) -> int:
        minimo = max(MINIMO_RANGO[0], min(MINIMO_RANGO[1], int(minimo)))
        with self._lock_ops:
            if self.acuses_min.get(servicio) == minimo:
                return minimo
            self.acuses_min[servicio] = minimo
            self._mini("MINIMO", f"{servicio}: mínimo de acuses = {minimo}")
            self._evaluar()
        return minimo

    def disponibilidad(self) -> dict:
        with self._lock_ops:
            return {s: {"vivas": len(self.vivas[s]), "minimo": self.acuses_min[s],
                        "habilitada": self.habilitadas[s],
                        "celulas": sorted((v[1], v[2] or "?") for v in self.vivas[s].values())}
                    for s in codigos.SERVICIOS}

    def operacion(self, id_operacion: str) -> dict | None:
        with self._lock_ops:
            op = self.operaciones.get(id_operacion)
            return self._fila(op) if op else None

    # ------------------------------------------------------------ recepción

    def procesar(self, m: dict) -> None:
        codigo = m["codigo"]
        if codigo == codigos.SRV_LAT:
            self._rx_latido(m)
            return
        partes = codigos.separar(codigo)
        if partes is None or partes[1] == codigos.REQ:
            self._ignorar(m, "no es para una GUI")
            return
        servicio, tipo = partes
        cuerpo = m["cuerpo"]
        op_id, intento = cuerpo.get("id_operacion"), cuerpo.get("intento")
        if tipo == codigos.ACK:  # un acuse también prueba que la célula vive
            self._marcar_viva(servicio, m["origen"], m.get("nombre_origen"), None)
        with self._lock_ops:
            op = self.operaciones.get(op_id) if isinstance(op_id, str) else None
            if op is None or op.servicio != servicio:
                mia = False
            else:
                mia = True
                if not isinstance(intento, int) or isinstance(intento, bool):
                    self.log("DROP", f"{codigo} {huella.corto(m['id'])} sin intento válido")
                    return
                if tipo == codigos.ACK:
                    self._rx_ack(op, m, intento)
                else:
                    self._rx_res(op, m)
        if not mia:
            self._ignorar(m, "operación ajena")

    def _ignorar(self, m: dict, por: str) -> None:
        self.ignorados += 1
        self.log("IGNORA", f"{m['codigo']} de {m.get('nombre_origen')} "
                           f"({huella.corto(m['id'])}): {por}", consola=False)

    def _rx_latido(self, m: dict) -> None:
        cuerpo = m["cuerpo"]
        servicio = cuerpo.get("servicio")
        if servicio not in codigos.SERVICIOS:
            return
        self._marcar_viva(servicio, m["origen"], m.get("nombre_origen"), cuerpo.get("nodo_nombre"))

    def _marcar_viva(self, servicio: str, h: str, nombre, nodo_nombre) -> None:
        nombre = nombre or huella.corto(h)
        with self._lock_ops:
            celulas = self.vivas[servicio]
            nueva = h not in celulas
            if nueva:
                celulas[h] = [time.monotonic(), nombre, nodo_nombre]
            else:
                celulas[h][0] = time.monotonic()
                celulas[h][1] = nombre
                if nodo_nombre:
                    celulas[h][2] = nodo_nombre
        if nueva:
            donde = f" en {nodo_nombre}" if nodo_nombre else ""
            self.log("VIVA", f"{servicio} {nombre} ({huella.corto(h)}){donde}")
            with self._lock_ops:
                self._evaluar(nueva=(servicio, nombre, h))

    def _rx_ack(self, op: Operacion, m: dict, intento: int) -> None:
        """Con ``_lock_ops`` tomado."""
        origen, nombre = m["origen"], m.get("nombre_origen") or huella.corto(m["origen"])
        if op.estado != EN_VUELO:
            self.log("ACUSE", f"de {nombre} para op {huella.corto(op.id)} ya {op.estado}; "
                              f"no cambia nada", consola=False)
            return
        op.acusadores.setdefault(intento, set()).add(origen)
        op.nombres[origen] = nombre
        minimo = self.acuses_min[op.servicio]
        if intento != op.intento:
            self._mini("ACUSE", f"de {nombre} ({huella.corto(origen)}) · intento {intento} "
                                f"(viejo: no cuenta para el intento {op.intento})")
            return
        self._mini("ACUSE", f"{op.acuses()}/{minimo} de {nombre} ({huella.corto(origen)}) "
                            f"· intento {intento}")
        if op.t_quorum is None and op.acuses() >= minimo:
            self._quorum(op)
        self._emitir_operacion(op)

    def _rx_res(self, op: Operacion, m: dict) -> None:
        """Con ``_lock_ops`` tomado."""
        nombre = m.get("nombre_origen") or huella.corto(m["origen"])
        rol = m["cuerpo"].get("rol")
        if op.estado == RESUELTA:
            self._mini("DUPLICADA", f"respuesta de {nombre} ({rol}) para op "
                                    f"{huella.corto(op.id)}: ya estaba resuelta; descartada")
            return
        if op.estado == FALLIDA:
            self._mini("TARDÍA", f"respuesta de {nombre} ({rol}) para op "
                                 f"{huella.corto(op.id)}: ya se dio por fallida; descartada")
            return
        if op.t_quorum is None:
            op.retenido = m
            self._mini("RETENIDA", f"respuesta de {nombre} ({rol}) retenida: aún sin quórum "
                                   f"({op.acuses()}/{self.acuses_min[op.servicio]})")
            return
        self._aceptar(op, m)

    # ---------------------------------------------------------- transiciones

    def _quorum(self, op: Operacion) -> None:
        op.t_quorum = time.monotonic()
        self._mini("QUÓRUM", f"{op.acuses()}/{self.acuses_min[op.servicio]} · intento "
                             f"{op.intento} · op {huella.corto(op.id)}")
        if op.retenido is not None:
            m, op.retenido = op.retenido, None
            self._aceptar(op, m)

    def _aceptar(self, op: Operacion, m: dict) -> None:
        cuerpo = m["cuerpo"]
        resultado, error = cuerpo.get("resultado"), cuerpo.get("error")
        if error is None and not _es_numero(resultado):
            error = f"respuesta sin resultado válido ({resultado!r})"[:120]
            resultado = None
        op.estado = RESUELTA
        op.resultado, op.error = resultado, (str(error) if error is not None else None)
        op.rol = str(cuerpo.get("rol") or "?")
        op.respondio = m.get("nombre_origen") or huella.corto(m["origen"])
        op.id_solicitud = cuerpo.get("id_solicitud")
        op.id_respuesta = m["id"]
        op.ms = round((time.monotonic() - op.t0) * 1000)
        self.en_vuelo = None
        texto = formato.operacion(op.a, op.servicio, op.b, op.resultado, op.error)
        self._mini("RESULTADO", f"{texto} · {op.rol} {op.respondio} · solicitud "
                                f"{huella.corto(op.id_solicitud)}… ↔ respuesta "
                                f"{huella.corto(op.id_respuesta)}… · {op.ms} ms")
        self._emitir_operacion(op)

    def _vencer(self, op: Operacion, motivo: str) -> None:
        if op.intento >= config.MAX_INTENTOS:
            op.estado = FALLIDA
            op.motivo = motivo
            op.ms = round((time.monotonic() - op.t0) * 1000)
            self.en_vuelo = None
            self._mini("FALLIDA", f"op {huella.corto(op.id)} "
                                  f"{formato.operacion(op.a, op.servicio, op.b)}: {motivo} "
                                  f"tras {op.intento} intento(s)")
            self._emitir_operacion(op)
            return
        op.intento += 1
        op.enviado_en = time.monotonic()
        op.t_quorum = None
        req = self.publicar(codigos.codigo(op.servicio, codigos.REQ),
                            {"id_operacion": op.id, "intento": op.intento, "a": op.a, "b": op.b})
        op.solicitudes[op.intento] = req["id"] if req else None
        self._mini("REINTENTO", f"op {huella.corto(op.id)} · intento {op.intento} ({motivo}) "
                                f"· solicitud nueva "
                                f"{huella.corto(op.solicitudes[op.intento]) or 'perdida'}")
        self._emitir_operacion(op)

    # ----------------------------------------------------------------- reloj

    def _vigilar(self) -> None:
        while not self._parar.wait(0.1):
            try:
                self._revisar()
            except Exception as e:
                self.log("ERROR", f"reloj: {e!r}")

    def _revisar(self) -> None:
        ahora = time.monotonic()
        with self._lock_ops:
            self._caducar(ahora)
            self._evaluar()
            op = self.operaciones.get(self.en_vuelo) if self.en_vuelo else None
            if op is None:
                return
            minimo = self.acuses_min[op.servicio]
            if op.t_quorum is None and op.acuses() >= minimo:
                self._quorum(op)  # p. ej. se bajó el mínimo en vivo
                if op.estado != EN_VUELO:
                    return
            if op.t_quorum is None:
                if ahora - op.enviado_en >= config.VENTANA_ACUSES:
                    self._vencer(op, f"acuses insuficientes ({op.acuses()}/{minimo})")
            else:
                plazo = (op.t_quorum + config.VENTANA_ELECCION
                         + config.RELEVO * max(1, op.acuses()) + config.MARGEN_RESULTADO)
                if ahora >= plazo:
                    self._vencer(op, "sin respuesta")

    def _caducar(self, ahora: float) -> None:
        """Con ``_lock_ops`` tomado. Sin enlace no se caduca a nadie (ver al_conectar)."""
        if self._sin_enlace or not self.conectado:
            return
        for servicio, celulas in self.vivas.items():
            for h, (visto, nombre, nodo_nombre) in list(celulas.items()):
                if ahora - visto > config.LATIDO_CADUCIDAD:
                    del celulas[h]
                    self.log("CADUCA", f"{servicio} {nombre} ({huella.corto(h)}) sin latido en "
                                       f"{config.LATIDO_CADUCIDAD:.0f} s; se da por muerta")

    def _evaluar(self, nueva: tuple | None = None) -> None:
        """Habilita o deshabilita operadores. Con ``_lock_ops`` tomado."""
        for s in codigos.SERVICIOS:
            n, m = len(self.vivas[s]), self.acuses_min[s]
            hab = n >= m
            if hab == self.habilitadas[s]:
                continue
            self.habilitadas[s] = hab
            if hab:
                extra = ""
                if nueva and nueva[0] == s:
                    extra = f" (nueva: {nueva[1]} · {huella.corto(nueva[2])})"
                self._mini("HABILITADA", f"{s} habilitada: {n}/{m}{extra}")
            else:
                self._mini("DESHABILITADA", f"{s} deshabilitada: {n} viva(s) < {m} mínima(s)")
        self._emitir_disponibilidad()

    # ------------------------------------------------------------- utilidades

    def _recortar_historial(self) -> None:
        while len(self.operaciones) > HISTORIAL:
            viejo = next(iter(self.operaciones))
            if viejo == self.en_vuelo:
                break
            del self.operaciones[viejo]

    def _fila(self, op: Operacion) -> dict:
        minimo = self.acuses_min[op.servicio]
        partes = [formato.operacion(op.a, op.servicio, op.b, op.resultado, op.error)]
        partes.append(f"acuses {op.acuses()}/{minimo}")
        if op.estado == RESUELTA:
            partes += [f"{op.rol} {op.respondio}", f"{op.ms} ms"]
        elif op.estado == FALLIDA:
            partes.append(f"FALLIDA: {op.motivo}")
        else:
            partes.append(f"intento {op.intento}")
        partes.append(f"op {huella.corto(op.id)}")
        return {"id": op.id, "servicio": op.servicio, "a": op.a, "b": op.b, "estado": op.estado,
                "intento": op.intento, "acuses": op.acuses(), "minimo": minimo,
                "resultado": op.resultado, "error": op.error, "rol": op.rol,
                "respondio": op.respondio, "ms": op.ms, "motivo": op.motivo,
                "id_solicitud": op.id_solicitud, "id_respuesta": op.id_respuesta,
                "texto": " · ".join(partes)}

    def _mini(self, evento: str, texto: str, *, registrar: bool = True) -> None:
        """Una línea del mini log de protocolo (y de la bitácora)."""
        if registrar:
            self.log(evento, texto)
        self._emitir("log", (hora(), evento, texto))

    def _emitir_operacion(self, op: Operacion) -> None:
        self._emitir("operacion", self._fila(op))

    def _emitir_disponibilidad(self, forzar: bool = False) -> None:
        disp = self.disponibilidad()
        if forzar or disp != self._ultima_disp:
            self._ultima_disp = disp
            self._emitir("disponibilidad", disp)
