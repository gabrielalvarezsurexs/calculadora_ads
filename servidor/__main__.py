"""py -m servidor --servicio SUM --nodo 127.0.0.1:5001 [--nombre SUM-N1] [--retardo-ms 0]

Célula servidor sin ventana: su bitácora va a consola y a logs/.
"""

import argparse
import sys
import time

from comun import codigos
from comun.bitacora import preparar_consola
from servidor.nucleo import Servidor


def main(argv=None) -> int:
    preparar_consola()
    p = argparse.ArgumentParser(prog="py -m servidor", description="Célula servidor (ADS)")
    p.add_argument("--servicio", required=True, type=str.upper, choices=codigos.SERVICIOS)
    p.add_argument("--nodo", required=True, help="endpoint host:puerto del nodo inicial")
    p.add_argument("--nombre", help="etiqueta para mostrar (por defecto <SERVICIO>-<puerto>)")
    p.add_argument("--retardo-ms", type=int, default=0,
                   help="retardo artificial al calcular, para demostrar el relevo")
    args = p.parse_args(argv)

    nombre = args.nombre or f"{args.servicio}-{args.nodo.rsplit(':', 1)[-1]}"
    try:
        servidor = Servidor(args.servicio, nombre, args.nodo, retardo_ms=args.retardo_ms)
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2
    servidor.iniciar()
    try:
        while servidor.activo:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        servidor.detener()
        servidor.bitacora.cerrar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
