"""Sonda de demo para el §11. NO forma parte del sistema ADS.

Se presenta ante un nodo como entidad SONDA, inyecta un mensaje SONDA_PRUEBA
(que ninguna célula procesa), imprime el id usado y termina.

    py -m sonda --nodo 127.0.0.1:5001                 # recorrido normal: FWD + DUP
    py -m sonda --nodo 127.0.0.1:5001 --ttl 1         # solo lo procesa el primer nodo
    py -m sonda --nodo 127.0.0.1:5001 --ttl 0         # el primer nodo lo descarta
    py -m sonda --nodo 127.0.0.1:5001 --repetir 3     # misma copia 3 veces: 1 FWD + 2 DUP ahí
    py -m sonda --nodo 127.0.0.1:5003 --id <hash>     # reinyecta un id ya visto: DUP en el Nodo 3

Ojo con ``--repetir``: las copias repetidas mueren en el primer nodo y nunca
llegan a los demás. Esa es justamente la evidencia de que no se retransmiten.
"""

import argparse
import socket
import sys
import threading

from comun import codigos, config, huella, mensajes
from comun.bitacora import preparar_consola
from comun.protocolo import Enlace


def main(argv=None) -> int:
    preparar_consola()
    p = argparse.ArgumentParser(prog="py -m sonda", description="Inyecta mensajes de prueba")
    p.add_argument("--nodo", required=True, help="endpoint host:puerto del nodo")
    p.add_argument("--ttl", type=int, default=config.TTL_INICIAL)
    p.add_argument("--id", help="id de mensaje a usar (64 hex); por defecto uno nuevo")
    p.add_argument("--repetir", type=int, default=1, help="veces que se manda la MISMA copia")
    p.add_argument("--nota", default="prueba de la sonda")
    p.add_argument("--nombre", default="SONDA")
    args = p.parse_args(argv)

    try:
        host, puerto = mensajes.separar_endpoint(args.nodo)
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2
    if args.id is not None and not mensajes.es_hash(args.id):
        print("[AVISO] el id no es un hash de 64 hex: el nodo lo descartará (DROP)")

    mi_hash = huella.de_entidad(mensajes.SONDA, args.nombre)
    respuesta = threading.Event()
    estado = {}

    def al_mensaje(enlace, m):
        if m.get("ctrl") in (mensajes.BIENVENIDA, mensajes.RECHAZO) and not respuesta.is_set():
            estado["respuesta"] = m
            respuesta.set()
        # Lo demás (el tráfico que el nodo le inunda) se ignora.

    try:
        sock = socket.create_connection((host, puerto), timeout=config.CONECTAR_TIMEOUT)
        sock.settimeout(None)
    except OSError as e:
        print(f"[ERROR] no se pudo conectar a {args.nodo}: {e}", file=sys.stderr)
        return 1
    enlace = Enlace(sock, saliente=True, endpoint=args.nodo, al_mensaje=al_mensaje,
                    al_cerrar=lambda e, motivo: respuesta.set(), etiqueta="sonda")
    enlace.enviar(mensajes.hola(mensajes.SONDA, mi_hash, args.nombre))
    enlace.iniciar()

    if not respuesta.wait(config.BIENVENIDA_TIMEOUT) or "respuesta" not in estado:
        print(f"[ERROR] {args.nodo} no contestó el HOLA", file=sys.stderr)
        enlace.cerrar("sin BIENVENIDA")
        return 1
    r = estado["respuesta"]
    if r["ctrl"] == mensajes.RECHAZO:
        print(f"[ERROR] {args.nodo} rechazó a la sonda: {r.get('motivo')}", file=sys.stderr)
        enlace.cerrar("rechazada")
        return 1
    print(f"Conectada a {r.get('nombre')} ({huella.corto(r.get('hash'))}); "
          f"nodos conocidos: {', '.join(r.get('nodos') or []) or 'ninguno'}")

    msg = mensajes.nuevo(codigos.SONDA_PRUEBA, mi_hash, mensajes.SONDA, args.nombre,
                         {"nota": args.nota}, ttl=args.ttl)
    if args.id is not None:
        msg["id"] = args.id
    for _ in range(max(1, args.repetir)):
        enlace.enviar(msg)

    print(f"Inyectado {codigos.SONDA_PRUEBA} ttl={args.ttl} ×{max(1, args.repetir)}")
    print(f"id={msg['id']}")
    enlace.cerrar("sonda terminó", vaciar=True)
    enlace.esperar(3)
    return 0


if __name__ == "__main__":
    sys.exit(main())
