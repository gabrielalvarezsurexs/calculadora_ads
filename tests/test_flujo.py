"""Sistema completo en proceso: 4 nodos, 16 servidores, 4 interfaces y una
célula espía que cuenta los ACK y RES de cada operación (§5, §9, §11).

Las aserciones de "exactamente un RES" esperan a que venzan TODOS los relevos
posibles (``asentar``): si hubiera una respuesta de más, el espía la vería.

Para provocar una titular lenta o muerta se usa un gancho en su bitácora: al
registrar TITULAR para esa operación, se le pone retardo o se detiene. Es el
mismo camino de código que ``--retardo-ms`` o que tumbar el proceso, pero sin
depender de a quién le toque ser titular.
"""

import time
import unittest
from unittest import mock

from comun import codigos, config, huella, mensajes
from interfaz.nucleo import EN_VUELO, FALLIDA, RESUELTA, Interfaz, Operacion
from servidor import nucleo as srv
from tests.apoyo import Espia, Registro, Sistema, acortar, esperar


def asentar() -> None:
    """Lo que tarda en vencer el último respaldo posible de una ronda."""
    time.sleep(config.VENTANA_ELECCION + 3 * config.RELEVO + 1.0)


class BaseFlujo(unittest.TestCase):
    sis: Sistema
    espia: Espia

    @classmethod
    def armar(cls) -> None:
        cls.sis = Sistema().completo()
        cls.espia = cls.sis.agregar(Espia(cls.sis.nodos[1].endpoint))
        assert esperar(lambda: cls.espia.conectado, 5)

    def operar(self, gui: Interfaz, servicio: str, a, b, plazo: float = 15.0) -> dict:
        op, texto = gui.solicitar(servicio, a, b)
        self.assertIsNotNone(op, texto)
        self.assertTrue(esperar(lambda: gui.operacion(op)["estado"] != EN_VUELO, plazo))
        return gui.operacion(op)

    def servidores(self, servicio: str):
        return [s for s in self.sis.servidores if s.servicio == servicio and s.activo]

    def reg(self, celula) -> Registro:
        return self.sis.registros[celula.nombre]

    def contar(self, servicio: str, evento: str, op: str) -> int:
        return sum(self.reg(s).contar(evento, f"op {huella.corto(op)}")
                   for s in self.sis.servidores if s.servicio == servicio)

    def afirmar_un_res(self, op: str, intento: int | None = None) -> dict:
        res = self.espia.respuestas(op)
        self.assertEqual(len(res), 1, [(m["nombre_origen"], m["cuerpo"]) for m in res])
        if intento is not None:
            self.assertEqual(res[0]["cuerpo"]["intento"], intento)
        return res[0]


class TestFlujo(BaseFlujo):
    @classmethod
    def setUpClass(cls):
        acortar(cls)
        cls.armar()
        cls.addClassCleanup(cls.sis.apagar)

    # ----------------------------------------------------- operaciones normales

    def test_cuatro_operaciones_un_solo_res(self):
        casos = [("SUM", 7, 5, 12), ("SUB", 10, 4, 6), ("MUL", 6, 7, 42), ("DIV", 7, 2, 3.5)]
        ids = []
        for gui, (s, a, b, _) in zip(self.sis.guis, casos, strict=True):
            op, texto = gui.solicitar(s, a, b)  # las cuatro a la vez, una por GUI
            self.assertIsNotNone(op, texto)
            ids.append(op)
        self.assertTrue(esperar(lambda: all(g.operacion(op)["estado"] != EN_VUELO
                                            for g, op in zip(self.sis.guis, ids, strict=True)), 15))
        asentar()
        for gui, op, (s, a, b, esperado) in zip(self.sis.guis, ids, casos, strict=True):
            with self.subTest(gui=gui.nombre, servicio=s):
                fila = gui.operacion(op)
                self.assertEqual(fila["estado"], RESUELTA)
                self.assertEqual(fila["resultado"], esperado)
                self.assertIsNone(fila["error"])
                self.assertGreaterEqual(fila["acuses"], config.ACUSES_MIN_DEFECTO)
                self.assertEqual(len(self.espia.acusadores(op)), 4, "acusan las 4 células")
                res = self.afirmar_un_res(op, 1)
                # Asociación solicitud ↔ respuesta (§10.2, §11).
                self.assertEqual(fila["id_respuesta"], res["id"])
                self.assertEqual(fila["id_solicitud"], res["cuerpo"]["id_solicitud"])
                self.assertNotEqual(fila["id_respuesta"], fila["id_solicitud"])
                self.assertEqual(fila["rol"], "titular")
                # En las bitácoras: 1 TITULAR, 3 respaldos que se liberan o se retiran.
                self.assertEqual(self.contar(s, "TITULAR", op), 1)
                self.assertEqual(self.contar(s, "LIBERADO", op) + self.contar(s, "RETIRADA", op),
                                 3)
                self.assertEqual(self.contar(s, "ACUSE", op), 4)
                self.assertEqual(self.contar(s, "RES", op), 1)
                # Las otras GUIs no registran la operación ajena.
                for otra in self.sis.guis:
                    if otra is not gui:
                        self.assertIsNone(otra.operacion(op), otra.nombre)
        for gui in self.sis.guis:
            self.assertGreater(self.reg(gui).contar("IGNORA", "no es para una GUI"), 0,
                               f"{gui.nombre} ve los REQ ajenos y los ignora")
            self.assertGreater(self.reg(gui).contar("IGNORA", "operación ajena"), 0)

    def test_division_entre_cero(self):
        fila = self.operar(self.sis.guis[1], "DIV", 1, 0)
        self.assertEqual(fila["estado"], RESUELTA)
        self.assertIsNone(fila["resultado"])
        self.assertEqual(fila["error"], "división entre cero")
        asentar()
        res = self.afirmar_un_res(fila["id"])
        self.assertEqual(res["cuerpo"]["error"], "división entre cero")

    def test_flotantes_y_negativos(self):
        fila = self.operar(self.sis.guis[2], "SUM", 0.1, -0.3)
        self.assertAlmostEqual(fila["resultado"], -0.2)

    # -------------------------------------------------------- respuesta única

    def test_titular_lenta_relevo_y_suprimida(self):
        gui = self.sis.guis[0]
        lentas = []

        def gancho(s, op8):
            def f(evento, texto):
                if evento == "TITULAR" and f"op {op8}" in texto:
                    s.retardo_ms = int((config.RELEVO * 2 + 1) * 1000)
                    lentas.append(s)
            return f

        op, _ = gui.solicitar("MUL", 9, 9)
        self.assertIsNotNone(op)
        mul = self.servidores("MUL")
        for s in mul:
            self.reg(s).ganchos.append(gancho(s, huella.corto(op)))
        try:
            self.assertTrue(esperar(lambda: gui.operacion(op)["estado"] != EN_VUELO, 15))
            fila = gui.operacion(op)
            self.assertEqual(fila["estado"], RESUELTA)
            self.assertEqual(fila["resultado"], 81)
            self.assertEqual(fila["rol"], "relevo 1")
            time.sleep(config.RELEVO * 2 + 1.5)  # que la lenta termine de calcular
            self.afirmar_un_res(op)
            self.assertEqual(len(lentas), 1)
            self.assertEqual(self.reg(lentas[0]).contar("SUPRIMIDA", f"op {huella.corto(op)}"), 1)
            self.assertEqual(self.contar("MUL", "RELEVO", op), 1)
        finally:
            for s in mul:
                self.reg(s).ganchos.clear()
                s.retardo_ms = 0

    # --------------------------------------------- rondas inyectadas a mano

    def publicar(self, servicio: str, tipo: str, op: str, intento: int, **extra) -> dict:
        m = self.espia.publicar(codigos.codigo(servicio, tipo),
                                {"id_operacion": op, "intento": intento, **extra})
        self.assertIsNotNone(m)
        return m

    def nueva_op(self, servicio: str) -> str:
        return huella.de_operacion(self.espia.hash, servicio, 0, 0)

    def test_reintento_mismo_id_operacion_atendido(self):
        """Regla ≤ k: el RES del intento 1 NO resuelve el intento 2. Un
        reintento significa que esa GUI no recibió la respuesta."""
        op = self.nueva_op("SUB")
        self.publicar("SUB", codigos.REQ, op, 1, a=5, b=3)
        self.assertTrue(esperar(lambda: len(self.espia.respuestas(op)) == 1, 10))
        self.publicar("SUB", codigos.REQ, op, 2, a=5, b=3)
        self.assertTrue(esperar(lambda: len(self.espia.respuestas(op)) == 2, 10))
        asentar()
        res = self.espia.respuestas(op)
        self.assertEqual([m["cuerpo"]["intento"] for m in res], [1, 2])
        self.assertEqual([m["cuerpo"]["resultado"] for m in res], [2, 2])

    def test_req_repetido_de_una_ronda_resuelta_no_responde(self):
        op = self.nueva_op("SUB")
        self.publicar("SUB", codigos.REQ, op, 1, a=1, b=1)
        self.assertTrue(esperar(lambda: len(self.espia.respuestas(op)) == 1, 10))
        self.publicar("SUB", codigos.REQ, op, 1, a=1, b=1)  # otra copia con id nuevo
        asentar()
        self.afirmar_un_res(op, 1)
        repetidos = sum(self.reg(s).contar("RX", f"op {huella.corto(op)} · intento 1 repetido")
                        for s in self.servidores("SUB"))
        self.assertEqual(repetidos, 4, "cada SUB lo reconoce como repetido y no vuelve a acusar")

    def test_ronda_vieja_superada_sin_respuesta_extra(self):
        """El reintento llega mientras la ronda 1 sigue en cola: la 1 queda
        superada y solo responde la 2."""
        op = self.nueva_op("DIV")
        self.publicar("DIV", codigos.REQ, op, 1, a=8, b=2)
        self.publicar("DIV", codigos.REQ, op, 2, a=8, b=2)
        self.assertTrue(esperar(lambda: self.espia.respuestas(op), 10))
        asentar()
        res = self.afirmar_un_res(op, 2)
        self.assertEqual(res["cuerpo"]["resultado"], 4)
        self.assertEqual(self.contar("DIV", "SUPERADA", op), 4)

    def test_req_viejo_que_llega_despues_del_nuevo(self):
        """Desorden en la malla: el REQ del intento 2 llega antes que el del 1.
        El 1 ya es historia: no debe generar otra respuesta.

        Sin la regla, el RES de más dependía de una carrera de milisegundos (se
        vio en 1 de 6 operaciones); por eso, además de contar respuestas, se
        exige que cada servidor marque el REQ tardío como SUPERADA."""
        ops = [self.nueva_op("DIV") for _ in range(6)]
        for op in ops:
            self.publicar("DIV", codigos.REQ, op, 2, a=9, b=3)
            self.publicar("DIV", codigos.REQ, op, 1, a=9, b=3)
        self.assertTrue(esperar(lambda: all(self.espia.respuestas(op) for op in ops), 15))
        asentar()
        for op in ops:
            with self.subTest(op=huella.corto(op)):
                self.afirmar_un_res(op, 2)
                self.assertEqual(self.contar("DIV", "SUPERADA", op), 4)
                self.assertEqual(self.contar("DIV", "TITULAR", op), 1)
                self.assertEqual(len(self.espia.acusadores(op, 1)), 0, "el tardío no se acusa")

    def test_ack_antes_del_req_ranking_correcto(self):
        """El ACK llega antes que el REQ (viajan por caminos distintos): se crea
        una ronda esqueleto que el REQ completa. El acusador "fantasma" entra al
        ranking; se elige una operación donde le toca rank 0, así que la titular
        nunca responde y lo hace el rank 1 con su relevo."""
        sumas = {s.hash: s for s in self.servidores("SUM")}
        while True:
            op = self.nueva_op("SUM")
            orden = huella.ranking({self.espia.hash, *sumas}, op, 1)
            if orden[0] == self.espia.hash:
                break
        self.publicar("SUM", codigos.ACK, op, 1)
        self.assertTrue(esperar(lambda: all(
            (op, 1) in s.rondas and s.rondas[(op, 1)].estado == srv.ESQUELETO
            for s in sumas.values()), 5))
        for s in sumas.values():
            self.assertEqual(s.rondas[(op, 1)].acusadores, {self.espia.hash})
            self.assertEqual(self.reg(s).contar("RX", "ronda esqueleto"), 1)
        self.publicar("SUM", codigos.REQ, op, 1, a=2, b=3)
        self.assertTrue(esperar(lambda: self.espia.respuestas(op), 10))
        asentar()
        res = self.afirmar_un_res(op, 1)
        self.assertEqual(res["origen"], orden[1])
        self.assertEqual(res["cuerpo"]["rol"], "relevo 1")
        self.assertEqual(res["cuerpo"]["resultado"], 5)
        for s in sumas.values():
            self.assertIn("de 5 [", " ".join(self.reg(s).eventos("RESPALDO", huella.corto(op))
                                              + self.reg(s).eventos("TITULAR", huella.corto(op))))


class TestFallas(BaseFlujo):
    """Cada prueba rompe algo, así que cada una arma su propio sistema."""

    @classmethod
    def setUpClass(cls):
        acortar(cls)

    def setUp(self):
        self.armar()
        self.addCleanup(self.sis.apagar)

    def test_titular_tumbada_despues_de_acusar(self):
        gui = self.sis.guis[2]
        muertas = []

        def gancho(s, op8):
            def f(evento, texto):
                if evento == "TITULAR" and f"op {op8}" in texto:
                    muertas.append(s)
                    s.detener()  # ya acusó; muere antes de publicar su RES
            return f

        op, _ = gui.solicitar("MUL", 3, 4)
        self.assertIsNotNone(op)
        for s in self.servidores("MUL"):
            self.reg(s).ganchos.append(gancho(s, huella.corto(op)))
        self.assertTrue(esperar(lambda: gui.operacion(op)["estado"] != EN_VUELO, 15))
        fila = gui.operacion(op)
        self.assertEqual((fila["estado"], fila["resultado"]), (RESUELTA, 12))
        self.assertEqual(fila["rol"], "relevo 1")
        asentar()
        self.afirmar_un_res(op)
        self.assertEqual(len(muertas), 1)
        self.assertEqual(self.reg(muertas[0]).contar("PERDIDO"), 1, "la titular no alcanzó a responder")
        self.assertNotEqual(self.espia.respuestas(op)[0]["origen"], muertas[0].hash)

    def test_tres_sum_tumbadas_deshabilita_y_una_nueva_habilita(self):
        sumas = self.servidores("SUM")
        for s in sumas[:3]:
            s.detener()
        guis = self.sis.guis
        self.assertTrue(esperar(lambda: not any(g.habilitadas["SUM"] for g in guis),
                                config.LATIDO_CADUCIDAD + 3))
        for g in guis:
            self.assertEqual(g.disponibilidad()["SUM"]["vivas"], 1)
            self.assertTrue(all(g.habilitadas[s] for s in ("SUB", "MUL", "DIV")))
            self.assertEqual(self.reg(g).contar("DESHABILITADA", "SUM"), 1)
        op, texto = guis[0].solicitar("SUM", 1, 1)
        self.assertIsNone(op)
        self.assertIn("no disponible", texto)

        self.sis.servidor("SUM", self.sis.nodos[0], "SUM-NUEVA")
        self.assertTrue(esperar(lambda: all(g.habilitadas["SUM"] for g in guis), 5))
        for g in guis:
            self.assertEqual(self.reg(g).contar("HABILITADA", "SUM-NUEVA"), 1)
        fila = self.operar(guis[0], "SUM", 1, 1)
        self.assertEqual((fila["estado"], fila["resultado"]), (RESUELTA, 2))
        asentar()
        self.afirmar_un_res(fila["id"])

    def test_nodo_tumbado_failover_y_el_servicio_sigue(self):
        # Caducidad real (6 s): el failover (~3 s) debe completarse sin que ninguna
        # GUI dé por muertas a las células que se están mudando de nodo.
        parche = mock.patch.object(config, "LATIDO_CADUCIDAD", 6.0)
        parche.start()
        self.addCleanup(parche.stop)
        n1 = self.sis.nodos[0]
        del1 = [c for c in self.sis.celulas if c.nodo_actual and c.nodo_actual["hash"] == n1.hash]
        self.assertEqual(len(del1), 5, "1 GUI + 4 servidores en el Nodo 1")
        hashes = {c.hash for c in del1}
        n1.detener()

        def migradas():
            return all(c.conectado and c.nodo_actual["hash"] != n1.hash for c in del1)
        self.assertTrue(esperar(migradas, 15))
        for c in del1:
            self.assertEqual(self.reg(c).contar("FAILOVER"), 1, c.nombre)
        # El hash de cada célula se conserva: los otros nodos la tienen en su tabla.
        en_tablas = set()
        for n in self.sis.nodos[1:]:
            en_tablas |= set(n.celulas)
        self.assertLessEqual(hashes, en_tablas)

        gui1 = self.sis.guis[0]
        for g in self.sis.guis:
            self.assertEqual(self.reg(g).contar("CADUCA"), 0, f"{g.nombre} no da por muerto a nadie")
        self.assertTrue(self.sis.esperar_disponible(4, 5))
        for s, a, b, r in (("SUM", 2, 2, 4), ("DIV", 9, 3, 3)):
            fila = self.operar(gui1, s, a, b)
            self.assertEqual((fila["estado"], fila["resultado"]), (RESUELTA, r))
        asentar()
        self.afirmar_un_res(fila["id"])


class TestReglasInterfaz(unittest.TestCase):
    """Las reglas de la GUI sin red: se le entregan mensajes con ``procesar``."""

    def setUp(self):
        self.registro = Registro("GUI-T")
        self.gui = Interfaz("GUI-T", "127.0.0.1:1", bitacora=self.registro.bitacora)
        self.celulas = {n: huella.de_entidad(mensajes.SERVIDOR, n, "SUM") for n in "ABC"}

    def msg(self, quien: str, tipo: str, cuerpo: dict, servicio: str = "SUM") -> dict:
        return mensajes.nuevo(codigos.codigo(servicio, tipo), self.celulas[quien],
                              mensajes.SERVIDOR, f"SUM-{quien}", cuerpo)

    def ack(self, quien, op, intento):
        self.gui.procesar(self.msg(quien, codigos.ACK, {"id_operacion": op.id,
                                                        "intento": intento}))

    def res(self, quien, op, intento, resultado):
        self.gui.procesar(self.msg(quien, codigos.RES, {
            "id_operacion": op.id, "intento": intento, "resultado": resultado, "error": None,
            "rol": "titular", "id_solicitud": "x"}))

    def en_vuelo(self, servicio="SUM") -> Operacion:
        op = Operacion(huella.de_operacion(self.gui.hash, servicio, 1, 2), servicio, 1, 2)
        with self.gui._lock_ops:
            self.gui.operaciones[op.id] = op
            self.gui.en_vuelo = op.id
        return op

    def vencer(self, op):
        with self.gui._lock_ops:
            self.gui._vencer(op, "prueba")

    def test_quorum_por_intento_y_res_retenido(self):
        op = self.en_vuelo()
        self.ack("A", op, 1)
        self.vencer(op)  # reintento: intento 2 (sin red, el REQ se pierde y se registra)
        self.assertEqual(op.intento, 2)
        self.assertEqual(self.registro.contar("PERDIDO"), 1)
        self.ack("B", op, 1)  # acuse viejo (B murió después de acusar el intento 1)
        self.assertEqual(op.acuses(), 0)
        self.ack("A", op, 2)
        self.assertEqual(op.acuses(), 1)
        self.assertIsNone(op.t_quorum, "un acuse viejo no completa el quórum")
        self.res("A", op, 2, 3)
        self.assertEqual(op.estado, EN_VUELO, "RES antes del quórum: se retiene")
        self.assertEqual(self.registro.contar("RETENIDA"), 1)
        self.ack("C", op, 2)
        self.assertIsNotNone(op.t_quorum)
        self.assertEqual((op.estado, op.resultado), (RESUELTA, 3), "con quórum se acepta el retenido")
        self.assertIsNone(self.gui.en_vuelo)
        self.res("B", op, 2, 3)
        self.assertEqual(self.registro.contar("DUPLICADA"), 1)
        self.assertEqual(op.respondio, "SUM-A")

    def test_fallida_y_tardia(self):
        op = self.en_vuelo()
        for _ in range(config.MAX_INTENTOS):
            self.vencer(op)
        self.assertEqual(op.estado, FALLIDA)
        self.assertEqual(op.intento, config.MAX_INTENTOS)
        self.assertIsNone(self.gui.en_vuelo)
        self.ack("A", op, 3)
        self.res("A", op, 3, 3)
        self.assertEqual(self.registro.contar("TARDÍA"), 1)
        self.assertEqual(op.estado, FALLIDA)

    def test_res_sin_resultado_valido_es_error(self):
        op = self.en_vuelo()
        self.ack("A", op, 1)
        self.ack("B", op, 1)
        self.gui.procesar(self.msg("A", codigos.RES, {"id_operacion": op.id, "intento": 1,
                                                      "resultado": "NaN", "error": None}))
        self.assertEqual(op.estado, RESUELTA)
        self.assertIsNone(op.resultado)
        self.assertIn("sin resultado válido", op.error)

    def test_ajenos_se_ignoran(self):
        op = self.en_vuelo()
        otra = huella.de_operacion("otra-gui", "SUM", 1, 2)
        self.gui.procesar(self.msg("A", codigos.REQ, {"id_operacion": otra, "intento": 1}))
        self.gui.procesar(self.msg("A", codigos.ACK, {"id_operacion": otra, "intento": 1}))
        self.gui.procesar(self.msg("A", codigos.RES, {"id_operacion": otra, "intento": 1}))
        self.gui.procesar(self.msg("A", codigos.ACK, {"id_operacion": op.id, "intento": 1},
                                   servicio="MUL"))  # mismo id, otro servicio
        self.assertEqual(self.gui.ignorados, 4)
        self.assertEqual(op.acuses(), 0)
        self.assertNotIn(otra, self.gui.operaciones)

    def test_disponibilidad_por_latidos(self):
        def latido(quien):
            self.gui.procesar(mensajes.nuevo(codigos.SRV_LAT, self.celulas[quien],
                                             mensajes.SERVIDOR, f"SUM-{quien}",
                                             {"servicio": "SUM", "nodo_nombre": "Nodo 1"}))

        self.assertFalse(self.gui.habilitadas["SUM"])
        latido("A")
        self.assertFalse(self.gui.habilitadas["SUM"], "1 viva < mínimo 2")
        latido("B")
        self.assertTrue(self.gui.habilitadas["SUM"])
        self.assertEqual(self.gui.ajustar_minimo("SUM", 3), 3)
        self.assertFalse(self.gui.habilitadas["SUM"])
        latido("C")
        self.assertTrue(self.gui.habilitadas["SUM"])
        self.assertEqual(self.gui.ajustar_minimo("SUM", 99), 16, "el mínimo se acota")
        self.assertEqual(self.gui.ajustar_minimo("SUM", 0), 1)
        self.assertFalse(any(self.gui.habilitadas[s] for s in ("SUB", "MUL", "DIV")))


if __name__ == "__main__":
    unittest.main()
