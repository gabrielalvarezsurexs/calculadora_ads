"""Hashes SHA-256 y el ranking HRW de la elección."""

import collections
import itertools
import random
import re
import unittest

from comun import huella

HEX64 = re.compile(r"[0-9a-f]{64}")


class TestHashes(unittest.TestCase):
    def test_64_hex(self):
        for h in (huella.generar("x"), huella.de_entidad("NODO", "Nodo 1"),
                  huella.de_mensaje("origen"), huella.de_operacion("gui", "SUM", 1, 2)):
            self.assertRegex(h, HEX64)

    def test_50000_unicos(self):
        hashes = {huella.de_mensaje("misma célula") for _ in range(50_000)}
        self.assertEqual(len(hashes), 50_000)

    def test_mismos_datos_hash_distinto(self):
        """Dos entidades con el mismo nombre (o dos operaciones idénticas) no chocan."""
        self.assertNotEqual(huella.de_entidad("SERVIDOR", "SUM-N1", "SUM"),
                            huella.de_entidad("SERVIDOR", "SUM-N1", "SUM"))
        self.assertNotEqual(huella.de_operacion("g", "SUM", 7, 5),
                            huella.de_operacion("g", "SUM", 7, 5))

    def test_corto(self):
        h = huella.generar("x")
        self.assertEqual(huella.corto(h), h[:8])
        self.assertEqual(huella.corto(None), "")


class TestRanking(unittest.TestCase):
    def setUp(self):
        self.celulas = [huella.de_entidad("SERVIDOR", f"SUM-N{k}", "SUM") for k in range(1, 5)]

    def test_determinista(self):
        op = huella.de_operacion("gui", "SUM", 1, 2)
        self.assertEqual(huella.ranking(self.celulas, op, 1), huella.ranking(self.celulas, op, 1))

    def test_independiente_del_orden_del_conjunto(self):
        """Cada célula arma su conjunto de acusadores en el orden en que le llegan
        los ACK; aun así todas deben calcular el mismo orden."""
        op = huella.de_operacion("gui", "SUM", 1, 2)
        esperado = huella.ranking(self.celulas, op, 1)
        for perm in itertools.permutations(self.celulas):
            self.assertEqual(huella.ranking(perm, op, 1), esperado)
            self.assertEqual(huella.ranking(set(perm), op, 1), esperado)

    def test_es_permutacion_del_conjunto(self):
        op = huella.de_operacion("gui", "SUM", 1, 2)
        self.assertCountEqual(huella.ranking(self.celulas, op, 1), self.celulas)

    def test_reparto_uniforme(self):
        """4 000 operaciones sobre 4 células: ~1 000 titularidades cada una.
        (σ binomial ≈ 27; el margen de ±150 es más de 5σ.)"""
        conteo = collections.Counter(
            huella.ranking(self.celulas, huella.de_operacion("gui", "SUM", i, i), 1)[0]
            for i in range(4000))
        self.assertEqual(set(conteo), set(self.celulas))
        for c in self.celulas:
            self.assertLess(abs(conteo[c] - 1000), 150, dict(conteo))

    def test_el_intento_cambia_la_titular(self):
        """El intento entra al hash: un reintento puede tocarle a otra célula
        (si la titular del intento 1 murió, no siempre es la misma)."""
        rng = random.Random(7)
        ops = [huella.de_operacion("gui", "SUM", rng.random(), 0) for _ in range(1000)]
        distintas = sum(huella.ranking(self.celulas, op, 1)[0] != huella.ranking(
            self.celulas, op, 2)[0] for op in ops)
        self.assertGreater(distintas, 650)  # se espera ~750 (3/4)
        self.assertLess(distintas, 850)

    def test_quitar_una_celula_no_reordena_a_las_demas(self):
        """Propiedad de HRW: si una acusadora falta, el orden relativo de las
        demás no cambia."""
        op = huella.de_operacion("gui", "MUL", 3, 4)
        completo = huella.ranking(self.celulas, op, 1)
        for quitada in self.celulas:
            resto = [c for c in self.celulas if c != quitada]
            self.assertEqual(huella.ranking(resto, op, 1), [c for c in completo if c != quitada])


if __name__ == "__main__":
    unittest.main()
