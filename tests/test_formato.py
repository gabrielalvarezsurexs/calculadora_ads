"""Formato de números y operaciones para humanos."""

import unittest

from comun import formato


class TestNumero(unittest.TestCase):
    def test_casos(self):
        casos = [(7.0, "7"), (7, "7"), (-3.0, "-3"), (0.0, "0"), (3.5, "3.5"),
                 (0.1 + 0.2, "0.3"), (1 / 3, "0.333333333333"), (1e20, "1e+20"),
                 (123456789012345.0, "123456789012345"), (1e15, "1e+15"), (2.5e-7, "2.5e-07"),
                 (None, "?"), (True, "True"), ("x", "x")]
        for valor, texto in casos:
            with self.subTest(valor=valor):
                self.assertEqual(formato.numero(valor), texto)


class TestOperacion(unittest.TestCase):
    def test_sin_resultado(self):
        self.assertEqual(formato.operacion(7, "DIV", 2), "7 ÷ 2")

    def test_con_resultado(self):
        self.assertEqual(formato.operacion(7, "DIV", 2, 3.5), "7 ÷ 2 = 3.5")
        self.assertEqual(formato.operacion(6.0, "MUL", 7.0, 42.0), "6 × 7 = 42")
        self.assertEqual(formato.operacion(1, "SUM", 1, 0.0), "1 + 1 = 0")

    def test_con_error(self):
        self.assertEqual(formato.operacion(1, "DIV", 0, error="división entre cero"),
                         "1 ÷ 0 → ERROR: división entre cero")

    def test_simbolos(self):
        for s, simbolo in (("SUM", "+"), ("SUB", "−"), ("MUL", "×"), ("DIV", "÷")):
            self.assertIn(f" {simbolo} ", formato.operacion(1, s, 2))

    def test_milisegundos(self):
        self.assertEqual(formato.milisegundos(0.0123), "12 ms")


if __name__ == "__main__":
    unittest.main()
