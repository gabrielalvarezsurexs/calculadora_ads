"""Protocolo de comunicación (§10.2, §11): inundación sin ciclos ni duplicados.

Malla de 4 con un ``Receptor`` en cada nodo. Los mensajes se inyectan con la
sonda real (``sonda.__main__.main``), igual que en la demo.
"""

import contextlib
import io
import re
import socket
import time
import unittest

from comun import codigos, config, huella, mensajes
from comun.protocolo import enviar, leer_mensajes, serializar
from sonda.__main__ import main as sonda
from tests.apoyo import Receptor, Sistema, acortar, esperar


def inyectar(nodo, *args) -> str:
    """Corre la sonda contra ``nodo`` y devuelve el id que usó."""
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida):
        codigo = sonda(["--nodo", nodo.endpoint, *map(str, args)])
    assert codigo == 0, salida.getvalue()
    return re.search(r"id=([0-9a-f]{64})", salida.getvalue()).group(1)


class TestBroadcast(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        acortar(cls)
        cls.sis = Sistema()
        cls.addClassCleanup(cls.sis.apagar)
        cls.nodos = cls.sis.malla(4)
        assert cls.sis.esperar_malla(), "la malla no se formó"
        cls.rec = [cls.sis.agregar(Receptor(f"REC-N{k}", n.endpoint))
                   for k, n in enumerate(cls.nodos, 1)]
        assert esperar(lambda: all(r.conectado for r in cls.rec), 5)
        time.sleep(0.3)

    def reg(self, nodo):
        return self.sis.registros[nodo.nombre]

    def fwd(self, nodo, id_mensaje) -> int:
        return self.reg(nodo).contar("FWD", f"#{huella.corto(id_mensaje)}")

    def dup(self, nodo, id_mensaje) -> int:
        return self.reg(nodo).contar("DUP", f"#{huella.corto(id_mensaje)}")

    def esperar_a_todos(self, id_mensaje):
        self.assertTrue(esperar(lambda: all(r.con_id(id_mensaje) for r in self.rec), 5))
        time.sleep(0.5)  # margen para que lleguen (y se descarten) las copias extra

    # ------------------------------------------------------------------ pruebas

    def test_llega_exactamente_una_vez_a_cada_celula(self):
        id_m = inyectar(self.nodos[0])
        self.esperar_a_todos(id_m)
        for r in self.rec:
            self.assertEqual(len(r.con_id(id_m)), 1, r.nombre)
            self.assertEqual(r.registro.contar("DUP", huella.corto(id_m)), 0,
                             f"{r.nombre}: el nodo no debe entregarle copias repetidas")
        for n in self.nodos:
            self.assertEqual(self.fwd(n, id_m), 1, f"{n.nombre} lo reenvía una sola vez")
        dups = [self.dup(n, id_m) for n in self.nodos]
        self.assertGreater(sum(dups), 0, "en una malla, las copias redundantes se ven como DUP")
        self.assertEqual(dups[0], 0, "nadie le regresa el mensaje al nodo de entrada (ruta)")

    def test_ruta_y_ttl(self):
        id_m = inyectar(self.nodos[0])
        self.esperar_a_todos(id_m)
        primero = self.nodos[0].hash
        for r, n in zip(self.rec, self.nodos, strict=True):
            (m,) = r.con_id(id_m)
            ruta = m["ruta"]
            with self.subTest(receptor=r.nombre):
                self.assertEqual(ruta[0], primero, "la ruta empieza en el nodo de entrada")
                self.assertEqual(ruta[-1], n.hash, "y termina en el nodo de la célula")
                self.assertEqual(len(set(ruta)), len(ruta), "sin nodos repetidos (sin ciclos)")
                self.assertEqual(m["ttl"], config.TTL_INICIAL - len(ruta))
                self.assertEqual(m["codigo"], codigos.SONDA_PRUEBA)
        (m1,) = self.rec[0].con_id(id_m)
        self.assertEqual(m1["ruta"], [primero])

    def test_ttl_1_solo_llega_a_las_celulas_del_primer_nodo(self):
        id_m = inyectar(self.nodos[0], "--ttl", 1)
        self.assertTrue(esperar(lambda: self.rec[0].con_id(id_m), 3))
        time.sleep(0.8)
        self.assertEqual(len(self.rec[0].con_id(id_m)), 1)
        for r in self.rec[1:]:
            self.assertEqual(r.con_id(id_m), [], r.nombre)
        self.assertEqual(self.fwd(self.nodos[0], id_m), 1)
        self.assertEqual(self.reg(self.nodos[0]).contar("TTL", huella.corto(id_m)), 1)
        for n in self.nodos[1:]:
            self.assertEqual(self.fwd(n, id_m) + self.dup(n, id_m), 0, n.nombre)

    def test_ttl_0_no_llega_a_nadie(self):
        id_m = inyectar(self.nodos[0], "--ttl", 0)
        self.assertTrue(esperar(
            lambda: self.reg(self.nodos[0]).contar("TTL", huella.corto(id_m)) == 1, 3))
        time.sleep(0.8)
        for r in self.rec:
            self.assertEqual(r.con_id(id_m), [])
        self.assertIn("ttl=0", self.reg(self.nodos[0]).eventos("TTL", huella.corto(id_m))[0])
        for n in self.nodos:
            self.assertEqual(self.fwd(n, id_m), 0)

    def test_ttl_excesivo_se_recorta(self):
        id_m = inyectar(self.nodos[0], "--ttl", 1000)
        self.esperar_a_todos(id_m)
        for r in self.rec:
            (m,) = r.con_id(id_m)
            self.assertLess(m["ttl"], config.TTL_MAX)

    def test_misma_copia_repetida_es_dup_en_el_nodo_de_entrada(self):
        """``sonda --repetir 3``: 1 FWD + 2 DUP ahí mismo; a las células les
        llega una vez."""
        id_m = inyectar(self.nodos[0], "--repetir", 3)
        self.esperar_a_todos(id_m)
        self.assertEqual(self.fwd(self.nodos[0], id_m), 1)
        self.assertEqual(self.reg(self.nodos[0]).contar("DUP", f"#{huella.corto(id_m)} de SONDA"), 2)
        for r in self.rec:
            self.assertEqual(len(r.con_id(id_m)), 1)

    def test_id_repetido_en_otro_nodo_es_dup(self):
        """``sonda --id <id>`` en el Nodo 3 con un id que ya circuló."""
        id_m = inyectar(self.nodos[0])
        self.esperar_a_todos(id_m)
        n3 = self.nodos[2]
        antes = self.dup(n3, id_m)
        self.assertEqual(inyectar(n3, "--id", id_m), id_m)
        self.assertTrue(esperar(lambda: self.dup(n3, id_m) == antes + 1, 3))
        time.sleep(0.5)
        self.assertEqual(self.fwd(n3, id_m), 1)
        for r in self.rec:
            self.assertEqual(len(r.con_id(id_m)), 1)

    def test_linea_basura_y_datos_sin_hola(self):
        """Una línea basura se descarta (DROP) y el enlace SIGUE vivo; datos antes
        del HOLA tampoco se procesan."""
        n1 = self.nodos[0]
        mi_hash = huella.de_entidad(mensajes.SONDA, "SUCIA")
        with socket.create_connection(("127.0.0.1", n1.puerto), timeout=3) as s:
            antes = self.reg(n1).contar("DROP")
            previo = mensajes.nuevo(codigos.SONDA_PRUEBA, mi_hash, mensajes.SONDA, "SUCIA", {})
            enviar(s, previo)  # antes de presentarse
            self.assertTrue(esperar(lambda: self.reg(n1).contar("DROP") == antes + 1, 3))
            enviar(s, mensajes.hola(mensajes.SONDA, mi_hash, "SUCIA"))
            m, _ = next(leer_mensajes(s))
            self.assertEqual(m["ctrl"], mensajes.BIENVENIDA)
            s.sendall(b"esto no es json\n" + b'{"id": "corto"}\n')
            bueno = mensajes.nuevo(codigos.SONDA_PRUEBA, mi_hash, mensajes.SONDA, "SUCIA", {})
            s.sendall(serializar(bueno))
            self.esperar_a_todos(bueno["id"])
            self.assertEqual(self.reg(n1).contar("DROP"), antes + 3)
            self.assertIn(mi_hash, n1.celulas, "el enlace sigue registrado")
            self.assertTrue(n1.celulas[mi_hash].vivo)
        for r in self.rec:
            self.assertEqual(r.con_id(previo["id"]), [], "lo enviado sin HOLA no circula")


if __name__ == "__main__":
    unittest.main()
