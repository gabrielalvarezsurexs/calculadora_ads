"""La lógica de negocio: función pura que nunca lanza."""

import math
import unittest

from servidor.calculo import calcular


class TestCalculo(unittest.TestCase):
    def test_cuatro_operaciones(self):
        casos = [("SUM", 7, 5, 12), ("SUB", 10, 4, 6), ("MUL", 6, 7, 42), ("DIV", 7, 2, 3.5),
                 ("SUM", -1.5, 0.5, -1), ("SUB", 0, 3, -3), ("MUL", -2, -2.5, 5),
                 ("DIV", -9, 3, -3)]
        for s, a, b, esperado in casos:
            with self.subTest(s=s, a=a, b=b):
                self.assertEqual(calcular(s, a, b), (esperado, None))

    def test_flotantes(self):
        r, e = calcular("SUM", 0.1, 0.2)
        self.assertIsNone(e)
        self.assertAlmostEqual(r, 0.3)

    def test_resultado_es_float(self):
        r, _ = calcular("SUM", 2, 3)
        self.assertIsInstance(r, float)

    def test_division_entre_cero(self):
        for b in (0, 0.0, -0.0):
            with self.subTest(b=b):
                self.assertEqual(calcular("DIV", 1, b), (None, "división entre cero"))
        self.assertEqual(calcular("DIV", 0, 0), (None, "división entre cero"))

    def test_resultado_no_finito(self):
        for s, a, b in (("MUL", 1e308, 10), ("SUM", 1.7e308, 1.7e308), ("DIV", 1e308, 1e-308),
                        ("SUB", -1.7e308, 1.7e308)):
            with self.subTest(s=s):
                r, e = calcular(s, a, b)
                self.assertIsNone(r)
                self.assertIn("fuera de rango", e)

    def test_operandos_no_finitos(self):
        for v in (math.inf, -math.inf, math.nan):
            with self.subTest(v=v):
                r, e = calcular("SUM", v, 1)
                self.assertIsNone(r)
                self.assertIn("no es finito", e)

    def test_entero_enorme(self):
        r, e = calcular("SUM", 10 ** 400, 1)
        self.assertIsNone(r)
        self.assertIn("fuera de rango", e)

    def test_bool_y_str_no_son_numeros(self):
        for a, b in ((True, 1), (1, False), ("7", 5), (1, "2"), (None, 1), ([1], 2), ({}, 1)):
            with self.subTest(a=a, b=b):
                r, e = calcular("SUM", a, b)
                self.assertIsNone(r)
                self.assertIn("no es un número", e)

    def test_servicio_desconocido(self):
        r, e = calcular("POW", 2, 3)
        self.assertIsNone(r)
        self.assertIn("no soportado", e)

    def test_exactamente_uno_es_none(self):
        for args in (("SUM", 1, 2), ("DIV", 1, 0), ("MUL", "x", 1), ("POW", 1, 1)):
            r, e = calcular(*args)
            self.assertTrue((r is None) != (e is None), args)

    def test_error_acotado(self):
        _, e = calcular("SUM", "x" * 1000, 1)
        self.assertLessEqual(len(e), 120)


if __name__ == "__main__":
    unittest.main()
