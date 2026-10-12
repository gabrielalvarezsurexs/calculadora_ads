"""py -m interfaz --nodo 127.0.0.1:5001 [--nombre GUI-1] [--acuses-min 2] [--geometria WxH+X+Y]

Célula GUI: la calculadora. La lógica vive en ``interfaz/nucleo.py``; la
ventana en ``interfaz/gui.py``.
"""

import argparse
import queue
import sys

from comun import config
from comun.bitacora import preparar_consola
from interfaz.nucleo import Interfaz


def main(argv=None) -> int:
    preparar_consola()
    p = argparse.ArgumentParser(prog="py -m interfaz", description="Célula GUI (ADS)")
    p.add_argument("--nodo", required=True, help="endpoint host:puerto del nodo inicial")
    p.add_argument("--nombre", help="etiqueta para mostrar (por defecto GUI-<puerto>)")
    p.add_argument("--acuses-min", type=int, default=config.ACUSES_MIN_DEFECTO,
                   help="mínimo de acuses por operación (se ajusta en vivo en la ventana)")
    p.add_argument("--geometria", help="geometría Tk de la ventana, p. ej. 420x640+0+0")
    args = p.parse_args(argv)

    nombre = args.nombre or f"GUI-{args.nodo.rsplit(':', 1)[-1]}"
    try:
        interfaz = Interfaz(nombre, args.nodo, acuses_min=args.acuses_min,
                            eventos=queue.Queue())
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2
    interfaz.iniciar()
    try:
        from interfaz.gui import VentanaInterfaz
        VentanaInterfaz(interfaz, geometria=args.geometria).ejecutar()
    except KeyboardInterrupt:
        pass
    finally:
        interfaz.detener()
        interfaz.bitacora.cerrar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
