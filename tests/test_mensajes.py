"""Sobre de datos, mensajes de control, endpoints y catálogo de códigos."""

import unittest

from comun import codigos, config, huella, mensajes

ORIGEN = huella.de_entidad(mensajes.INTERFAZ, "GUI-1")


def sobre(**cambios) -> dict:
    m = mensajes.nuevo("SUM_REQ", ORIGEN, mensajes.INTERFAZ, "GUI-1", {"a": 1})
    m.update(cambios)
    return m


class TestSobre(unittest.TestCase):
    def test_nuevo(self):
        m = mensajes.nuevo("SUM_REQ", ORIGEN, mensajes.INTERFAZ, "GUI-1", {"a": 1, "b": 2})
        self.assertEqual(set(m), {"id", "codigo", "origen", "tipo_origen", "nombre_origen", "ts",
                                  "ttl", "ruta", "cuerpo"})
        self.assertTrue(mensajes.es_hash(m["id"]))
        self.assertNotEqual(m["id"], ORIGEN)
        self.assertEqual(m["codigo"], "SUM_REQ")
        self.assertEqual(m["origen"], ORIGEN)
        self.assertEqual(m["ttl"], config.TTL_INICIAL)
        self.assertEqual(m["ruta"], [])
        self.assertEqual(m["cuerpo"], {"a": 1, "b": 2})
        self.assertIsNone(mensajes.validar_datos(m))

    def test_ttl_explicito_incluso_cero(self):
        self.assertEqual(mensajes.nuevo("X", ORIGEN, "SONDA", "s", {}, ttl=0)["ttl"], 0)
        self.assertEqual(mensajes.nuevo("X", ORIGEN, "SONDA", "s", {}, ttl=3)["ttl"], 3)

    def test_ids_distintos(self):
        self.assertNotEqual(sobre()["id"], sobre()["id"])

    def test_validar_cada_campo(self):
        casos = {
            "id corto": {"id": "abc"},
            "id mayúsculas": {"id": "A" * 64},
            "id ausente": {"id": None},
            "codigo vacío": {"codigo": ""},
            "codigo no texto": {"codigo": 5},
            "origen no texto": {"origen": None},
            "ttl texto": {"ttl": "8"},
            "ttl flotante": {"ttl": 8.0},
            "ttl bool": {"ttl": True},
            "ruta no lista": {"ruta": "N1"},
            "ruta con números": {"ruta": [1, 2]},
            "cuerpo lista": {"cuerpo": [1]},
            "cuerpo ausente": {"cuerpo": None},
        }
        for nombre, cambio in casos.items():
            with self.subTest(nombre):
                self.assertIsNotNone(mensajes.validar_datos(sobre(**cambio)))
        self.assertIsNotNone(mensajes.validar_datos([1, 2]))
        self.assertIsNone(mensajes.validar_datos(sobre(ttl=0)))  # ttl 0 es válido: lo frena el nodo


class TestControl(unittest.TestCase):
    H = huella.generar("x")

    def test_hola_valido(self):
        self.assertIsNone(mensajes.validar_hola(
            mensajes.hola(mensajes.NODO, self.H, "Nodo 1", escucha=5001)))
        self.assertIsNone(mensajes.validar_hola(
            mensajes.hola(mensajes.SERVIDOR, self.H, "SUM-N1", "SUM")))
        self.assertIsNone(mensajes.validar_hola(mensajes.hola(mensajes.INTERFAZ, self.H, "GUI")))

    def test_hola_invalido(self):
        base = mensajes.hola(mensajes.NODO, self.H, "Nodo 1", escucha=5001)
        casos = {
            "versión": ({"version": 99}, mensajes.MOTIVO_VERSION),
            "entidad": ({"entidad": "IMPOSTOR"}, mensajes.INVALIDO),
            "hash": ({"hash": "123"}, mensajes.INVALIDO),
            "nombre vacío": ({"nombre": ""}, mensajes.INVALIDO),
            "servicio no texto": ({"servicio": 3}, mensajes.INVALIDO),
            "nodo sin escucha": ({"escucha": None}, mensajes.INVALIDO),
            "escucha bool": ({"escucha": True}, mensajes.INVALIDO),
            "escucha fuera de rango": ({"escucha": 70000}, mensajes.INVALIDO),
        }
        for nombre, (cambio, motivo) in casos.items():
            with self.subTest(nombre):
                problema = mensajes.validar_hola({**base, **cambio})
                self.assertIsNotNone(problema)
                self.assertEqual(problema[0], motivo)

    def test_control_lleva_ctrl_y_no_codigo(self):
        for m in (mensajes.hola(mensajes.SONDA, self.H, "s"),
                  mensajes.bienvenida(self.H, "Nodo 1", ["127.0.0.1:5002"]),
                  mensajes.pares(["127.0.0.1:5002"]),
                  mensajes.rechazo(mensajes.DUPLICADO, self.H)):
            self.assertIn("ctrl", m)
            self.assertNotIn("codigo", m)


class TestEndpoints(unittest.TestCase):
    def test_separar(self):
        self.assertEqual(mensajes.separar_endpoint("127.0.0.1:5001"), ("127.0.0.1", 5001))
        self.assertEqual(mensajes.separar_endpoint(" localhost:80 "), ("localhost", 80))

    def test_separar_invalidos(self):
        for ep in ("127.0.0.1", "127.0.0.1:", ":5001", "a b:1", "h:0", "h:70000", "h:x", None, 5):
            with self.subTest(ep=ep), self.assertRaises(ValueError):
                mensajes.separar_endpoint(ep)

    def test_endpoints_validos_filtra(self):
        self.assertEqual(mensajes.endpoints_validos(["127.0.0.1:5001", "basura", 3, "h:0",
                                                     " h:22 "]), ["127.0.0.1:5001", "h:22"])
        self.assertEqual(mensajes.endpoints_validos("127.0.0.1:5001"), [])
        self.assertEqual(mensajes.endpoints_validos(None), [])


class TestCatalogo(unittest.TestCase):
    def test_completo(self):
        esperado = {f"{s}_{t}" for s in ("SUM", "SUB", "MUL", "DIV") for t in ("REQ", "ACK", "RES")}
        esperado |= {"SRV_LAT", "SONDA_PRUEBA"}
        self.assertEqual(set(codigos.CATALOGO), esperado)

    def test_ida_y_vuelta(self):
        for s in codigos.SERVICIOS:
            for t in codigos.TIPOS:
                self.assertEqual(codigos.separar(codigos.codigo(s, t)), (s, t))

    def test_separar_no_operacion(self):
        for c in ("SRV_LAT", "SONDA_PRUEBA", "POW_REQ", "SUM_XXX", "SUM", "", None, 3):
            with self.subTest(c=c):
                self.assertIsNone(codigos.separar(c))

    def test_cada_servicio_tiene_nombre_y_simbolo(self):
        for s in codigos.SERVICIOS:
            self.assertIn(s, codigos.NOMBRES)
            self.assertIn(s, codigos.SIMBOLOS)


if __name__ == "__main__":
    unittest.main()
