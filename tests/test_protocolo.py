"""Framing NDJSON sin sockets reales.

``leer_mensajes`` acepta cualquier objeto con ``.recv(n)``; ``FuenteFalsa``
(del primer parcial) entrega los bytes exactamente en los trozos que se le den,
para simular que TCP parte o junta mensajes como quiera.
"""

import json
import unittest
from unittest import mock

from comun import config
from comun.protocolo import ConexionCerrada, leer_mensajes, serializar


class FuenteFalsa:
    def __init__(self, trozos: list[bytes]):
        self._trozos = list(trozos)

    def recv(self, _n: int) -> bytes:
        return self._trozos.pop(0) if self._trozos else b""


def _hasta_cierre(fuente: FuenteFalsa):
    try:
        yield from leer_mensajes(fuente)
    except ConexionCerrada:
        return


def leer_todo(trozos: list[bytes]) -> list[tuple]:
    """Todos los pares (mensaje, problema) hasta el cierre."""
    return list(_hasta_cierre(FuenteFalsa(trozos)))


def solo_mensajes(pares) -> list[dict]:
    return [m for m, p in pares if p is None]


class TestFraming(unittest.TestCase):
    def test_un_mensaje(self):
        self.assertEqual(leer_todo([b'{"a": 1}\n']), [({"a": 1}, None)])

    def test_mensaje_partido(self):
        crudo = serializar({"codigo": "SUM_REQ", "texto": "partido a la mitad, con ñ"})
        for corte in (1, len(crudo) // 2, len(crudo) - 1):
            with self.subTest(corte=corte):
                pares = leer_todo([crudo[:corte], crudo[corte:]])
                self.assertEqual(solo_mensajes(pares),
                                 [{"codigo": "SUM_REQ", "texto": "partido a la mitad, con ñ"}])

    def test_byte_por_byte(self):
        crudo = serializar({"x": "ü"}) + serializar({"y": 2})
        pares = leer_todo([bytes([b]) for b in crudo])
        self.assertEqual(solo_mensajes(pares), [{"x": "ü"}, {"y": 2}])

    def test_mensajes_pegados(self):
        pares = leer_todo([b'{"t": "a"}\n{"t": "b"}\n{"t": "c"}\n'])
        self.assertEqual(solo_mensajes(pares), [{"t": "a"}, {"t": "b"}, {"t": "c"}])

    def test_lineas_vacias_se_ignoran(self):
        self.assertEqual(leer_todo([b'\n\r\n  \n{"a": 1}\r\n']), [({"a": 1}, None)])

    def test_cierre_lanza_conexion_cerrada(self):
        gen = leer_mensajes(FuenteFalsa([b'{"a": 1}\n']))
        self.assertEqual(next(gen), ({"a": 1}, None))
        with self.assertRaises(ConexionCerrada):
            next(gen)

    def test_cierre_con_linea_a_medias_no_la_entrega(self):
        self.assertEqual(leer_todo([b'{"a": 1}\n{"b": ']), [({"a": 1}, None)])


class TestLineasInvalidas(unittest.TestCase):
    """Una línea mala se reporta y la lectura SIGUE (el lector no muere)."""

    def test_linea_invalida_no_rompe_el_lector(self):
        pares = leer_todo([b'{"a": 1}\nesto no es json\n{"b": 2}\n'])
        self.assertEqual(len(pares), 3)
        self.assertEqual(pares[0], ({"a": 1}, None))
        self.assertIsNone(pares[1][0])
        self.assertIn("JSON", pares[1][1])
        self.assertEqual(pares[2], ({"b": 2}, None))

    def test_json_que_no_es_objeto(self):
        pares = leer_todo([b'[1, 2]\n"texto"\n42\n{"ok": true}\n'])
        self.assertEqual([p for _, p in pares[:3]], ["no es un objeto JSON"] * 3)
        self.assertEqual(pares[3], ({"ok": True}, None))

    def test_utf8_invalido(self):
        pares = leer_todo([b'{"a": "\xff\xfe"}\n{"b": 1}\n'])
        self.assertIsNone(pares[0][0])
        self.assertEqual(pares[1], ({"b": 1}, None))

    def test_nan_e_infinity_se_rechazan_al_leer(self):
        pares = leer_todo([b'{"x": NaN}\n{"x": Infinity}\n{"x": -Infinity}\n{"x": 1.5}\n'])
        self.assertEqual([m for m, _ in pares], [None, None, None, {"x": 1.5}])


class TestTopeMaxLinea(unittest.TestCase):
    def setUp(self):
        parche = mock.patch.object(config, "MAX_LINEA", 100)
        parche.start()
        self.addCleanup(parche.stop)

    def test_linea_larga_completa_se_descarta(self):
        larga = b'{"x": "' + b"a" * 200 + b'"}\n'
        pares = leer_todo([larga + b'{"ok": 1}\n'])
        self.assertIsNone(pares[0][0])
        self.assertIn("máx. 100", pares[0][1])
        self.assertEqual(pares[1], ({"ok": 1}, None))

    def test_linea_larga_en_trozos_sin_salto(self):
        """Más de MAX_LINEA sin '\\n': se avisa UNA vez, se tira el resto de esa
        línea (aunque llegue en más trozos) y la siguiente se lee bien."""
        trozos = [b'{"x": "' + b"a" * 150, b"a" * 150, b'a"}\n{"ok": 2}\n']
        pares = leer_todo(trozos)
        problemas = [p for m, p in pares if m is None]
        self.assertEqual(len(problemas), 1)
        self.assertIn("sin salto de línea", problemas[0])
        self.assertEqual(solo_mensajes(pares), [{"ok": 2}])

    def test_linea_justo_en_el_tope_pasa(self):
        relleno = 100 - len(b'{"x": ""}')
        linea = b'{"x": "' + b"a" * relleno + b'"}'
        self.assertEqual(len(linea), 100)
        self.assertEqual(solo_mensajes(leer_todo([linea + b"\n"])), [{"x": "a" * relleno}])


class TestSerializar(unittest.TestCase):
    def test_una_linea_terminada_en_salto(self):
        datos = serializar({"a": "ñ", "b": [1, 2]})
        self.assertTrue(datos.endswith(b"\n"))
        self.assertEqual(datos.count(b"\n"), 1)
        self.assertEqual(json.loads(datos), {"a": "ñ", "b": [1, 2]})

    def test_salto_dentro_de_un_texto_se_escapa(self):
        datos = serializar({"t": "dos\nlíneas"})
        self.assertEqual(datos.count(b"\n"), 1)
        self.assertEqual(solo_mensajes(leer_todo([datos])), [{"t": "dos\nlíneas"}])

    def test_allow_nan_false(self):
        for valor in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                serializar({"x": valor})


if __name__ == "__main__":
    unittest.main()
