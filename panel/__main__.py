"""py -m panel

Panel de despliegue para la demo. NO forma parte del sistema ADS: solo lanza
procesos del sistema operativo con los mismos comandos que se pueden escribir a
mano.
"""

import sys

from comun.bitacora import preparar_consola
from panel.gui import VentanaPanel
from panel.procesos import Gestor


def main() -> int:
    preparar_consola()
    VentanaPanel(Gestor()).ejecutar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
