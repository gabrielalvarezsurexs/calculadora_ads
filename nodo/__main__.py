"""py -m nodo --puerto 5001 --nombre "Nodo 1" [--semillas 127.0.0.1:5002,...] [--sin-ventana]

Basta una semilla cualquiera (o ninguna, si es el primer nodo): el resto de la
malla se descubre por gossip.
"""

import argparse
import queue
import sys
import time

from comun.bitacora import preparar_consola
from nodo.nucleo import Nodo


def main(argv=None) -> int:
    preparar_consola()
    p = argparse.ArgumentParser(prog="py -m nodo", description="Nodo del Campo de Datos (ADS)")
    p.add_argument("--puerto", type=int, required=True)
    p.add_argument("--nombre", help='etiqueta para mostrar (por defecto "Nodo <puerto>")')
    p.add_argument("--host", default="127.0.0.1",
                   help="interfaz donde escuchar; 0.0.0.0 para LAN (por defecto 127.0.0.1)")
    p.add_argument("--semillas", default="",
                   help="endpoints host:puerto de nodos conocidos, separados por comas")
    p.add_argument("--sin-ventana", action="store_true", help="correr sin ventana (headless)")
    p.add_argument("--geometria", help="geometría Tk de la ventana, p. ej. 720x450+0+0")
    args = p.parse_args(argv)

    nombre = args.nombre or f"Nodo {args.puerto}"
    semillas = [s.strip() for s in args.semillas.split(",") if s.strip()]
    eventos = None if args.sin_ventana else queue.Queue()
    nodo = Nodo(args.puerto, nombre, host=args.host, semillas=semillas, eventos=eventos)
    try:
        nodo.iniciar()
    except OSError as e:
        texto = (f"{nombre}: no se pudo escuchar en {args.host}:{args.puerto} ({e}). "
                 f"¿El puerto ya está ocupado?")
        nodo.bitacora("ERROR", texto, consola=False)
        nodo.bitacora.cerrar()
        print(f"[ERROR] {texto}", file=sys.stderr, flush=True)
        return 1

    try:
        if args.sin_ventana:
            while nodo.activo:
                time.sleep(0.5)
        else:
            from nodo.gui import VentanaNodo
            VentanaNodo(nodo, geometria=args.geometria).ejecutar()
    except KeyboardInterrupt:
        pass
    finally:
        nodo.detener()
        nodo.bitacora.cerrar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
