"""La bitácora nunca lanza (plan §6): ni con la consola rota ni con un callback
que falla. Así un proceso sobrevive a que se cierre el panel que lo leía."""

import io
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from comun.bitacora import Bitacora


class ConsolaRota(io.TextIOBase):
    def write(self, _s):
        raise OSError("pipe roto")

    def flush(self):
        raise OSError("pipe roto")

    def close(self):  # al recolectarla, IOBase llamaría a flush y ensuciaría la salida
        pass


class TestBitacora(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.carpeta = Path(tmp.name)

    def test_formato_y_archivo(self):
        b = Bitacora("SUM N1", "ab" * 32, consola=False, carpeta=self.carpeta)
        b("FWD", "hola ñ")
        b.cerrar()
        self.assertEqual(b.ruta.name, "SUM_N1-abababab.log")
        linea = b.ruta.read_text(encoding="utf-8").strip()
        self.assertRegex(linea, r"^\d\d:\d\d:\d\d\.\d{3} \[FWD\] hola ñ$")

    def test_consola_rota_no_lanza_y_el_archivo_sigue(self):
        b = Bitacora("x", consola=True, carpeta=self.carpeta)
        with mock.patch.object(sys, "stdout", ConsolaRota()):
            b("INICIO", "uno")
            b("FWD", "dos")
        b.cerrar()
        eventos = re.findall(r"\[(\w+)\]", b.ruta.read_text(encoding="utf-8"))
        self.assertEqual(eventos, ["INICIO", "FWD"])

    def test_solo_archivo(self):
        salida = io.StringIO()
        b = Bitacora("x", consola=True, carpeta=self.carpeta)
        with mock.patch.object(sys, "stdout", salida):
            b("IGNORA", "ruido", consola=False)
            b("RES", "señal")
        b.cerrar()
        self.assertNotIn("ruido", salida.getvalue())
        self.assertIn("señal", salida.getvalue())
        self.assertIn("ruido", b.ruta.read_text(encoding="utf-8"))

    def test_callback_que_falla_no_lanza(self):
        def malo(*_):
            raise RuntimeError("ventana cerrada")
        b = Bitacora("x", consola=False, archivo=False, callback=malo)
        b("FWD", "no revienta")

    def test_escribir_despues_de_cerrar_no_lanza(self):
        b = Bitacora("x", consola=False, carpeta=self.carpeta)
        b.cerrar()
        b("FWD", "tarde")


if __name__ == "__main__":
    unittest.main()
