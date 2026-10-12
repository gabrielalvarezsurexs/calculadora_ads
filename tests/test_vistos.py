"""Registro temporal de ids ya procesados (§11)."""

import threading
import unittest

from comun.vistos import RegistroVistos


class RelojFalso:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class TestRegistroVistos(unittest.TestCase):
    def test_nuevo_y_repetido(self):
        r = RegistroVistos(vigencia=60, maximo=100)
        self.assertTrue(r.marcar_si_nuevo("a"))
        self.assertFalse(r.marcar_si_nuevo("a"))
        self.assertFalse(r.marcar_si_nuevo("a"))
        self.assertTrue(r.marcar_si_nuevo("b"))
        self.assertTrue(r.contiene("a"))
        self.assertEqual(len(r), 2)

    def test_caducidad_con_reloj_falso(self):
        reloj = RelojFalso()
        r = RegistroVistos(vigencia=60, maximo=100, reloj=reloj)
        r.marcar_si_nuevo("viejo")
        reloj.t += 30
        r.marcar_si_nuevo("medio")
        reloj.t += 29.9
        self.assertFalse(r.marcar_si_nuevo("viejo"), "a los 59.9 s todavía se recuerda")
        reloj.t += 0.2
        self.assertFalse(r.contiene("viejo"), "a los 60.1 s ya se olvidó")
        self.assertTrue(r.contiene("medio"))
        self.assertEqual(len(r), 1)
        self.assertTrue(r.marcar_si_nuevo("viejo"), "olvidado: vuelve a ser nuevo (lo frena el TTL)")
        reloj.t += 61
        self.assertEqual(len(r), 0)

    def test_tope_olvida_los_mas_viejos(self):
        r = RegistroVistos(vigencia=60, maximo=3)
        for x in "abcd":
            r.marcar_si_nuevo(x)
        self.assertEqual(len(r), 3)
        self.assertFalse(r.contiene("a"))
        self.assertTrue(all(r.contiene(x) for x in "bcd"))

    def test_atomico_con_hilos(self):
        """Muchos hilos traen la MISMA copia a la vez: exactamente uno la ve nueva
        (solo uno la reenviaría)."""
        r = RegistroVistos(vigencia=60, maximo=10_000)
        for ronda in range(50):
            barrera = threading.Barrier(16)
            nuevos = []

            def trabajar(id_mensaje=f"m{ronda}", barrera=barrera, nuevos=nuevos):
                barrera.wait()
                if r.marcar_si_nuevo(id_mensaje):
                    nuevos.append(1)

            hilos = [threading.Thread(target=trabajar) for _ in range(16)]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join()
            self.assertEqual(len(nuevos), 1, f"ronda {ronda}")


if __name__ == "__main__":
    unittest.main()
