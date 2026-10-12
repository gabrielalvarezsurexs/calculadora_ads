"""El Enlace: cola de escritura que no bloquea, desborde → LENTO, y un lector
que sobrevive a líneas inválidas y a callbacks que fallan."""

import socket
import threading
import time
import unittest
from unittest import mock

from comun import config
from comun.protocolo import Enlace, leer_mensajes, serializar
from tests.apoyo import esperar


class Recolector:
    def __init__(self):
        self.mensajes, self.problemas, self.cierres = [], [], []
        self.cerrado = threading.Event()

    def al_mensaje(self, _e, m):
        self.mensajes.append(m)

    def al_problema(self, _e, p):
        self.problemas.append(p)

    def al_cerrar(self, _e, motivo):
        self.cierres.append(motivo)
        self.cerrado.set()


class BaseEnlace(unittest.TestCase):
    def setUp(self):
        self.a, self.b = socket.socketpair()
        self.addCleanup(self.a.close)
        self.addCleanup(self.b.close)
        self.r = Recolector()

    def enlace(self, sock=None, **extra) -> Enlace:
        e = Enlace(sock or self.a, True, "par:1", al_mensaje=self.r.al_mensaje,
                   al_problema=self.r.al_problema, al_cerrar=self.r.al_cerrar,
                   bitacora=lambda *a, **k: None, **extra)
        self.addCleanup(e.cerrar, "fin de la prueba")
        return e.iniciar()


class TestEscritura(BaseEnlace):
    def test_enviar_no_bloquea_aunque_el_par_no_lea(self):
        """El par nunca lee: los buffers del SO se llenan y el escritor se atora
        en sendall, pero ``enviar`` (quien difunde) regresa de inmediato."""
        e = self.enlace()
        datos = b"x" * 65536 + b"\n"
        t0 = time.monotonic()
        for _ in range(200):  # ~13 MB, mucho más que los buffers del socket
            self.assertTrue(e.enviar_bytes(datos))
        self.assertLess(time.monotonic() - t0, 1.0)
        self.assertTrue(e.vivo)

    def test_desborde_cierra_con_lento(self):
        with mock.patch.object(config, "COLA_ENLACE_MAX", 20):
            e = self.enlace()
            datos = b"x" * 262144 + b"\n"
            resultados = [e.enviar_bytes(datos) for _ in range(60)]
        self.assertIn(False, resultados)
        self.assertFalse(e.vivo)
        self.assertTrue(e.motivo_cierre.startswith("LENTO"))
        self.assertTrue(self.r.cerrado.wait(3))
        time.sleep(0.2)
        self.assertEqual(len(self.r.cierres), 1, "al_cerrar se llama exactamente una vez")
        self.assertFalse(e.enviar({"tarde": True}), "un enlace cerrado ya no acepta datos")

    def test_los_mensajes_salen_en_orden(self):
        e = self.enlace()
        for i in range(500):
            e.enviar({"i": i})
        recibidos = []
        gen = leer_mensajes(self.b)
        while len(recibidos) < 500:
            m, _ = next(gen)
            recibidos.append(m["i"])
        self.assertEqual(recibidos, list(range(500)))

    def test_cerrar_vaciando_entrega_lo_pendiente(self):
        e = self.enlace()
        e.enviar({"ultimo": "RECHAZO"})
        e.cerrar("rechazado", vaciar=True)
        m, _ = next(leer_mensajes(self.b))
        self.assertEqual(m, {"ultimo": "RECHAZO"})


class TestLectura(BaseEnlace):
    def test_linea_invalida_no_tumba_el_enlace(self):
        e = self.enlace()
        self.b.sendall(b"basura\n" + serializar({"ok": 1}))
        self.assertTrue(esperar(lambda: self.r.mensajes == [{"ok": 1}], 3))
        self.assertEqual(len(self.r.problemas), 1)
        self.assertTrue(e.vivo)

    def test_callback_que_falla_no_mata_al_lector(self):
        errores = []
        vistos = []

        def al_mensaje(_e, m):
            vistos.append(m)
            if m.get("explota"):
                raise RuntimeError("falla del dueño")

        e = Enlace(self.a, False, al_mensaje=al_mensaje, al_cerrar=self.r.al_cerrar,
                   bitacora=lambda ev, t, **k: errores.append(ev)).iniciar()
        self.addCleanup(e.cerrar)
        self.b.sendall(serializar({"explota": True}) + serializar({"despues": 1}))
        self.assertTrue(esperar(lambda: len(vistos) == 2, 3))
        self.assertEqual(errores, ["ERROR"])
        self.assertTrue(e.vivo)

    def test_cierre_del_par_llama_al_cerrar_una_vez(self):
        e = self.enlace()
        self.b.close()
        self.assertTrue(self.r.cerrado.wait(3))
        self.assertFalse(e.vivo)
        e.cerrar("otra vez")  # idempotente
        time.sleep(0.1)
        self.assertEqual(self.r.cierres, ["cerrado por el par"])


if __name__ == "__main__":
    unittest.main()
