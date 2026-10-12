"""Copia los minutos del video de GUION_VIDEO.md a la matriz de trazabilidad del reporte.

Herramienta de documentación, fuera del sistema.

    py docs/llenar_minutos.py --revisar   # muestra qué minuto va en cada fila, sin escribir
    py docs/llenar_minutos.py             # escribe la columna "Video" del §2 de REPORTE_TECNICO.md

Lee dos tablas de GUION_VIDEO.md:
- "Minutos por escena" (| Escena | Título | Minuto |): el minuto en que empieza cada escena.
- "Matriz del reporte" (| § | Requisito | Escena | Minuto |): una fila por cada fila de la
  matriz que se demuestra en el video, en el mismo orden. Si su "Minuto" está vacío, toma el de
  su escena.

Solo toca las filas de la matriz cuya columna "Video" no es "—". Antes de escribir verifica que
coincidan con las del guion (mismo § y mismo requisito, en el mismo orden) y que todos los
minutos tengan la forma m:ss o mm:ss. Se puede volver a correr si se corrige un minuto.
"""

import argparse
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MINUTO = re.compile(r"^\d{1,2}:[0-5]\d$")
SIN_VIDEO = "—"
PENDIENTE = "<mm:ss>"


def celdas(linea: str) -> list[str]:
    return [c.strip() for c in linea.strip().strip("|").split("|")]


def valor(celda: str) -> str:
    """El minuto escrito en una celda, o "" si está vacía o sigue el marcador."""
    texto = celda.strip().strip("`").strip()
    return "" if texto in ("", PENDIENTE) else texto


def tabla_bajo(lineas: list[str], titulo: str) -> list[tuple[int, list[str]]]:
    """(número de línea, celdas) de cada fila de la primera tabla bajo el encabezado ``titulo``,
    sin la fila de títulos ni la de separadores."""
    inicio = next((i for i, linea in enumerate(lineas)
                   if linea.startswith("#") and linea.lstrip("#").strip() == titulo), None)
    if inicio is None:
        raise ValueError(f"no encontré el encabezado {titulo!r}")
    filas = []
    for i in range(inicio + 1, len(lineas)):
        linea = lineas[i].strip()
        if linea.startswith("|"):
            filas.append((i, celdas(linea)))
        elif filas or linea.startswith("#"):
            break
    if len(filas) < 3:
        raise ValueError(f"no hay tabla bajo {titulo!r}")
    return filas[2:]


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="py docs/llenar_minutos.py", description=__doc__.split("\n")[0])
    p.add_argument("--revisar", action="store_true", help="solo mostrar; no escribir")
    p.add_argument("--guion", type=Path, default=RAIZ / "GUION_VIDEO.md")
    p.add_argument("--reporte", type=Path, default=RAIZ / "REPORTE_TECNICO.md")
    args = p.parse_args(argv)

    guion = args.guion.read_text(encoding="utf-8").splitlines()
    crudo = args.reporte.read_bytes()
    salto = "\r\n" if b"\r\n" in crudo else "\n"
    reporte = crudo.decode("utf-8").splitlines()

    try:
        escenas = {c[0]: valor(c[-1]) for _, c in tabla_bajo(guion, "Minutos por escena")}
        pedidas = [c for _, c in tabla_bajo(guion, "Matriz del reporte")]
        matriz = [(i, c) for i, c in tabla_bajo(reporte, "2. Matriz de trazabilidad con el enunciado")
                  if c[-1] != SIN_VIDEO]
    except ValueError as e:
        print(f"[ERROR] {e}")
        return 1

    errores = []
    if len(pedidas) != len(matriz):
        errores.append(f"el guion tiene {len(pedidas)} filas y la matriz del reporte "
                       f"{len(matriz)} con video")
    sin_minuto = sorted({c[2] for c in pedidas if not valor(c[3]) and not escenas.get(c[2])},
                        key=lambda s: int(s) if s.isdigit() else 0)
    if sin_minuto:
        errores.append(f"falta el minuto de la(s) escena(s) {', '.join(sin_minuto)}")
    cambios = []
    for n, (pedida, (i, fila)) in enumerate(zip(pedidas, matriz), start=1):
        seccion, requisito, escena = pedida[0], pedida[1], pedida[2]
        if (seccion, requisito) != (fila[0], fila[1]):
            errores.append(f"fila {n}: el guion dice §{seccion} {requisito!r} y el reporte "
                           f"§{fila[0]} {fila[1]!r}")
            continue
        minuto = valor(pedida[3]) or escenas.get(escena, "")
        if minuto and not MINUTO.match(minuto):
            errores.append(f"fila {n} (§{seccion}): {minuto!r} no tiene la forma mm:ss")
        cambios.append((i, seccion, escena, minuto, requisito))
    if errores:
        for e in errores:
            print(f"[ERROR] {e}")
        print("No se escribió nada.")
        return 1

    for i, seccion, escena, minuto, requisito in cambios:
        print(f"§{seccion:<5} escena {escena:>2}  {minuto:>5}  {requisito}")
    if args.revisar:
        print(f"{len(cambios)} fila(s). Sin --revisar se escriben en {args.reporte.name}.")
        return 0
    for i, _, _, minuto, _ in cambios:
        cabeza, _, _ = reporte[i].rstrip().rsplit("|", 2)
        reporte[i] = f"{cabeza}| {minuto} |"
    args.reporte.write_text(salto.join(reporte) + salto, encoding="utf-8", newline="")
    print(f"{len(cambios)} fila(s) escritas en {args.reporte.name}. "
          f"Falta regenerar el .docx: py docs/md_a_docx.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
