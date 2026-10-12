"""Protocolo de conexión (§10.1): la malla completa se forma sola desde una
semilla cualquiera, sin enlaces duplicados, y se repara cuando cae un nodo."""

import socket
import time
import unittest

from comun import mensajes
from comun.protocolo import enviar, leer_mensajes
from nodo.nucleo import Nodo
from tests.apoyo import Receptor, Registro, Sistema, acortar, esperar, puertos_libres


def mismo_enlace(a: Nodo, b: Nodo) -> bool:
    """El vecino b de a y el vecino a de b son los DOS extremos de la misma
    conexión TCP (y no dos conexiones distintas)."""
    ea, eb = a.vecinos.get(b.hash), b.vecinos.get(a.hash)
    if ea is None or eb is None or not (ea.vivo and eb.vivo):
        return False
    try:
        return ea.sock.getsockname() == eb.sock.getpeername()
    except OSError:
        return False


def enlaces_de_nodo_vivos(n: Nodo) -> int:
    with n._lock:
        return sum(1 for e in n._enlaces if e.vivo and e.presentado
                   and e.entidad == mensajes.NODO)


class TestMalla(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        acortar(cls)

    def setUp(self):
        self.sis = Sistema()
        self.addCleanup(self.sis.apagar)

    def afirmar_malla_completa(self, nodos):
        for a in nodos:
            self.assertEqual(len(a.vecinos), len(nodos) - 1, a.nombre)
            self.assertEqual(enlaces_de_nodo_vivos(a), len(nodos) - 1,
                             f"{a.nombre}: hay enlaces de nodo de más")
            for b in nodos:
                if a is not b:
                    self.assertTrue(mismo_enlace(a, b), f"{a.nombre}↔{b.nombre}")

    def test_cadena_de_semillas_forma_la_malla_completa(self):
        """Cada nodo solo conoce al anterior; el gossip completa la malla."""
        nodos = self.sis.malla(4)
        self.assertTrue(self.sis.esperar_malla())
        time.sleep(1.0)  # que se asienten los enlaces sobrantes de marcados cruzados
        self.afirmar_malla_completa(nodos)
        for n in nodos:
            self.assertEqual(self.sis.registros[n.nombre].contar("DESCONEXION"), 0,
                             f"{n.nombre}: un enlace sobrante no es una caída (sale DUPLICADO)")
        for n in nodos:
            self.assertEqual(sorted(n.conocidos), sorted(m.endpoint for m in nodos if m is not n))
            fila = n.instantanea()
            self.assertEqual(len(fila["vecinos"]), 3)
            self.assertEqual({v["nombre"] for v in fila["vecinos"]},
                             {m.nombre for m in nodos if m is not n})

    def test_marcado_simultaneo_converge_a_un_enlace(self):
        """Dos nodos que se conocen mutuamente arrancan a la vez y se marcan al
        mismo tiempo: la regla de enlace duplicado deja UNO, igual en ambos lados."""
        for vuelta in range(5):
            with self.subTest(vuelta=vuelta):
                sis = Sistema()
                try:
                    pa, pb = puertos_libres(2)
                    ra, rb = Registro("A"), Registro("B")
                    a = Nodo(pa, "A", semillas=[f"127.0.0.1:{pb}"], bitacora=ra.bitacora)
                    b = Nodo(pb, "B", semillas=[f"127.0.0.1:{pa}"], bitacora=rb.bitacora)
                    sis.nodos += [a, b]
                    a.iniciar()
                    b.iniciar()
                    self.assertTrue(sis.esperar_malla(5))
                    time.sleep(1.0)  # varios ciclos de supervisor: no debe oscilar
                    self.afirmar_malla_completa([a, b])
                    self.assertEqual(ra.contar("DESCONEXION") + rb.contar("DESCONEXION"), 0,
                                     "resolver el duplicado no es una caída")
                finally:
                    sis.apagar()

    def test_autoconexion_rechazada(self):
        """Un alias del propio endpoint ('localhost' en vez de 127.0.0.1) no se
        reconoce hasta marcar: el nodo se contesta RECHAZO(autoconexion), lo
        anota como propio y no lo vuelve a intentar."""
        reg = Registro("Solo")
        n = Nodo(0, "Solo", bitacora=reg.bitacora)
        self.sis.nodos.append(n)
        n.iniciar()
        alias = f"localhost:{n.puerto}"
        n._aprender([alias])
        self.assertTrue(esperar(lambda: alias in n.propios, 10))
        self.assertGreaterEqual(reg.contar("RECHAZO", "autoconexion"), 1)
        rechazos = reg.contar("RECHAZO")
        time.sleep(1.0)
        self.assertEqual(reg.contar("RECHAZO"), rechazos, "no reintenta un endpoint propio")
        self.assertEqual(n.vecinos, {})

    def test_quinto_nodo_con_una_sola_semilla(self):
        nodos = self.sis.malla(4)
        self.assertTrue(self.sis.esperar_malla())
        quinto = self.sis.nodo("Nodo 5", [nodos[2].endpoint])  # solo conoce al Nodo 3
        self.assertTrue(self.sis.esperar_malla())
        time.sleep(1.0)
        self.afirmar_malla_completa(nodos + [quinto])

    def test_tumbar_un_nodo_lo_saca_de_las_tablas(self):
        nodos = self.sis.malla(4)
        self.assertTrue(self.sis.esperar_malla())
        caido = nodos[3]
        caido.detener()
        vivos = nodos[:3]
        self.assertTrue(esperar(lambda: all(caido.hash not in n.vecinos for n in vivos), 5))
        for n in vivos:
            self.assertEqual(self.sis.registros[n.nombre].contar("DESCONEXION", caido.nombre), 1)
        # Los demás siguen en malla entre sí y siguen intentando al caído sin romperse.
        # (En Windows, el rechazo de un connect() a localhost tarda ~2 s.)
        self.assertTrue(esperar(lambda: all(self.sis.registros[n.nombre].contar("INALCANZABLE")
                                            for n in vivos), 8))
        self.afirmar_malla_completa(vivos)

    def test_nodo_que_vuelve_en_el_mismo_puerto_reingresa(self):
        nodos = self.sis.malla(3)
        self.assertTrue(self.sis.esperar_malla())
        puerto = nodos[0].puerto
        nodos[0].detener()
        self.sis.nodos.remove(nodos[0])
        self.assertTrue(esperar(lambda: all(len(n.vecinos) == 1 for n in nodos[1:]), 5))
        nuevo = self.sis.nodo("Nodo 1", puerto=puerto)  # sin semillas: lo buscan los demás
        self.assertTrue(self.sis.esperar_malla(10))
        time.sleep(1.0)
        self.afirmar_malla_completa([nuevo] + nodos[1:])

    def test_celulas_en_su_tabla_y_hola_invalido(self):
        """Las células van a la tabla de células (no a vecinos), con su tipo. Un
        HOLA de entidad desconocida recibe RECHAZO."""
        (n,) = self.sis.malla(1)
        rec = self.sis.agregar(Receptor("REC", n.endpoint))
        self.assertTrue(esperar(lambda: rec.hash in n.celulas, 5))
        fila = n.instantanea()
        self.assertEqual(fila["vecinos"], [])
        self.assertEqual([(c["nombre"], c["entidad"]) for c in fila["celulas"]],
                         [("REC", mensajes.SONDA)])

        with socket.create_connection(("127.0.0.1", n.puerto), timeout=3) as s:
            enviar(s, {**mensajes.hola(mensajes.SONDA, "a" * 64, "x"), "entidad": "IMPOSTOR"})
            m, _ = next(leer_mensajes(s))
        self.assertEqual((m["ctrl"], m["motivo"]), (mensajes.RECHAZO, mensajes.INVALIDO))


if __name__ == "__main__":
    unittest.main()
