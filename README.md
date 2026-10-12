# Calculadora ADS

Proyecto del **segundo parcial de Cómputo Distribuido**. Es la calculadora del primer parcial
pasada a una **arquitectura ADS**: ya no hay middleware ni servidor central. Hay un **Campo de
Datos** de nodos en malla completa, y las células (GUI y servidores) se comunican solo por
**broadcast con Códigos de Contenido** (`SUM_REQ`, `SUM_RES`, …).

**Python 3 con librería estándar únicamente.** Sin dependencias externas, sin base de datos, sin
frameworks: sockets TCP, hilos y Tkinter.

| Entregable | Dónde |
|---|---|
| **Reporte técnico** | [REPORTE_TECNICO.md](REPORTE_TECNICO.md) · versión `.docx` en `Reporte_Tecnico_Calculadora_ADS.docx` |
| **Video de demostración** | ver la portada del reporte |
| **Código fuente** | este repositorio: célula cliente en [interfaz/](interfaz/), célula servidor en [servidor/](servidor/) y nodo en [nodo/](nodo/) |

---

## Qué hace

```
   GUI-1 SUM-N1 SUB-N1 MUL-N1 DIV-N1            GUI-2 SUM-N2 SUB-N2 MUL-N2 DIV-N2
          \    \    |    /    /                        \    \   |   /    /
           [ NODO 1 :5001 ] ═══════════════════════ [ NODO 2 :5002 ]
                 ║        ╲                       ╱        ║
                 ║          ╲                   ╱          ║     malla completa:
                 ║            ═══════╳═════════            ║     cada nodo ↔ los otros 3
                 ║          ╱                   ╲          ║
           [ NODO 3 :5003 ] ═══════════════════════ [ NODO 4 :5004 ]
          /    /    |    \    \                        /    /   |   \    \
   GUI-3 SUM-N3 SUB-N3 MUL-N3 DIV-N3            GUI-4 SUM-N4 SUB-N4 MUL-N4 DIV-N4
```

Alguien teclea `7 + 5` en la GUI-1:

1. La GUI publica un `SUM_REQ` con un id único. Su nodo lo **inunda** por la malla.
2. Los nodos descartan las copias repetidas (`DUP`) y **nunca abren el contenido**.
3. Las 4 células `SUM` lo reciben, **acusan de inmediato** (`SUM_ACK`) y lo encolan.
4. Las 4 calculan el mismo ranking por hash entre las que acusaron. **Una sola, la titular,
   responde** `SUM_RES`; las demás quedan de respaldo escalonado por si la titular falla.
5. La respuesta también se inunda. Solo la GUI-1 la toma, porque la operación es suya; las otras
   GUIs la ignoran por código e id.

No hay ningún componente indispensable: si se cae un nodo, sus células se pasan solas a otro; si
se cae la titular, responde un respaldo; si quedan menos servidores vivos que el mínimo de
acuses, la GUI deshabilita ese operador hasta que alguien se levante.

---

## Arrancar

Requisito: Python 3.12 o más reciente (se desarrolló con 3.14; en Windows se usa `py`). No hay
nada que instalar.

```powershell
py -m panel
```

En el panel, **"Levantar configuración mínima"** levanta los 4 nodos y sus 20 células (4 GUIs y
16 servidores). Las ventanas de nodo y de GUI se acomodan solas; los servidores no tienen ventana
y su bitácora se ve en el panel al seleccionarlos.

> El panel es una herramienta de demostración y **no forma parte del sistema**: solo lanza
> procesos del sistema operativo con los mismos comandos que se pueden escribir a mano (los muestra
> en su lista). Si se cierra sin detener los procesos, el sistema sigue funcionando.

Desde el panel también se puede:
- levantar (▶) o tumbar (■) cualquier célula o nodo en la matriz;
- agregar un nodo más con **"+ Nodo"**;
- levantar servidores lentos con el campo **"retardo ms"** (para ver el relevo).

### A mano (cada comando en su propia terminal, desde esta carpeta)

```powershell
py -m nodo --puerto 5001 --nombre "Nodo 1"
py -m nodo --puerto 5002 --nombre "Nodo 2" --semillas 127.0.0.1:5001
py -m nodo --puerto 5003 --nombre "Nodo 3" --semillas 127.0.0.1:5002
py -m nodo --puerto 5004 --nombre "Nodo 4" --semillas 127.0.0.1:5001

py -m servidor --servicio SUM --nodo 127.0.0.1:5001 --nombre SUM-N1
py -m servidor --servicio DIV --nodo 127.0.0.1:5003 --nombre DIV-N3 --retardo-ms 4000
py -m interfaz --nodo 127.0.0.1:5002 --nombre GUI-2 --acuses-min 2
```

| Programa | Opciones |
|---|---|
| `py -m nodo` | `--puerto` (obligatorio), `--nombre`, `--semillas host:puerto,...`, `--host` (127.0.0.1 por defecto; `0.0.0.0` para LAN), `--sin-ventana`, `--geometria` |
| `py -m servidor` | `--servicio SUM\|SUB\|MUL\|DIV`, `--nodo host:puerto`, `--nombre`, `--retardo-ms` |
| `py -m interfaz` | `--nodo host:puerto`, `--nombre`, `--acuses-min` (2 por defecto), `--geometria` |
| `py -m sonda` | `--nodo host:puerto`, `--ttl`, `--repetir N`, `--id <hash>` |

Basta con que cada nodo conozca **a uno cualquiera** de los demás: el resto lo descubre solo y la
malla queda completa. Con más nodos o más células no se cambia nada del código.

### Sonda (prevención de ciclos y duplicados)

La sonda es otra herramienta de demostración fuera del sistema. Inyecta un mensaje de prueba que
ninguna célula procesa, para ver en las ventanas de los nodos cómo se comporta la inundación:

```powershell
py -m sonda --nodo 127.0.0.1:5002              # recorrido normal: 1 FWD por nodo y DUP en los demás
py -m sonda --nodo 127.0.0.1:5002 --ttl 1      # solo lo procesa el Nodo 2 (TTL agotado)
py -m sonda --nodo 127.0.0.1:5002 --repetir 3  # la misma copia 3 veces: 1 FWD + 2 DUP en el Nodo 2
py -m sonda --nodo 127.0.0.1:5003 --id <id>    # reinyecta un id ya visto en otro nodo: DUP
```

### Pruebas

```powershell
py -m unittest discover -s tests -t .   # 106 pruebas, ~85 s, sin ventanas ni red externa
```

Las bitácoras de cada proceso quedan en `logs/<nombre>-<hash8>.log`.

---

## ¿Dónde está cada cosa?

| Si buscas... | Está en |
|---|---|
| **El reporte técnico** | [REPORTE_TECNICO.md](REPORTE_TECNICO.md) |
| **Qué requisito del enunciado cumple qué archivo** | Matriz de trazabilidad, §2 del reporte |
| **El nodo del Campo de Datos** | [nodo/nucleo.py](nodo/nucleo.py): conexión, malla, broadcast y defensas contra ciclos |
| **La célula servidor** | [servidor/nucleo.py](servidor/nucleo.py): acuse, cola, elección, relevo y latidos |
| **La célula GUI** | [interfaz/nucleo.py](interfaz/nucleo.py) (lógica) y [interfaz/gui.py](interfaz/gui.py) (ventana) |
| **Lo común a toda célula** (conexión, failover) | [celula/base.py](celula/base.py) |
| **Las 4 operaciones** | [servidor/calculo.py](servidor/calculo.py): función pura |
| **El formato de los mensajes** | [comun/mensajes.py](comun/mensajes.py) y §5–§6 del reporte |
| **Los Códigos de Contenido** | [comun/codigos.py](comun/codigos.py) |
| **Los hashes y el ranking de elección** | [comun/huella.py](comun/huella.py) |
| **Todas las constantes de tiempo** | [comun/config.py](comun/config.py) |
| **El plan de diseño completo** | [docs/PLAN.md](docs/PLAN.md) |
| **El guion del video** (escenas, comandos y qué se ve en cada una) | [GUION_VIDEO.md](GUION_VIDEO.md) |

```
comun/      transporte NDJSON + Enlace, hashes, códigos, mensajes, config, registro de vistos,
            bitácora, formato de números
nodo/       nodo del Campo de Datos (nucleo.py sin Tkinter, gui.py la ventana)
celula/     célula base (lo común: conexión, failover, deduplicación, publicar)
servidor/   célula servidor (calculo.py, nucleo.py)
interfaz/   célula GUI (nucleo.py sin Tkinter, gui.py la ventana)
panel/      herramienta de despliegue para la demo (fuera del sistema)
sonda/      herramienta para inyectar mensajes de prueba (fuera del sistema)
tests/      106 pruebas unitarias y de integración
```

---

## Decisiones de diseño

| Decisión | Por qué |
|---|---|
| **Nodos "bobos"**: aceptan conexiones, inundan y evitan ciclos, pero nunca leen el contenido | En ADS el significado de un mensaje es asunto de las células. El nodo no necesita cambiar si aparece un servicio nuevo |
| **Todo es broadcast**; cada célula filtra por Código de Contenido | Lo pide el enunciado (§9) y es lo que hace que nadie tenga que saber quién atiende qué |
| **Todo tiene un hash SHA-256** que genera la propia entidad | Nadie asigna identidades, así que no hay un punto central que pueda fallar |
| **Malla por gossip**: basta una semilla cualquiera | Ningún nodo es especial; agregar un nodo no requiere configurar a los demás |
| **Cuatro defensas contra ciclos**: id + registro temporal, TTL, ruta y horizonte dividido, y deduplicación en la célula | Cada una cubre un hueco de las otras (detalle en §8 del reporte) |
| **Acuse inmediato y elección por hash (HRW)** entre las células que acusaron | Una sola respuesta sin coordinador ni mensajes extra; los respaldos escalonados cubren a la titular si falla |
| **Disponibilidad por latidos** (`SRV_LAT`) | La GUI sabe al instante cuántos servidores vivos hay y deshabilita un operador si no alcanzan el mínimo |
| **Failover de células** a otro nodo de la malla | Si se cae un nodo, sus células no quedan aisladas |
| **Los `nucleo.py` no importan Tkinter** | Tkinter no es seguro entre hilos; y así las pruebas levantan el sistema completo sin ventanas |
| **Solo librería estándar** | Cero instalación: basta `py -m panel` |

---

## Reutilización de código

Del primer parcial (mismo autor) se adaptaron el framing NDJSON (`comun/protocolo.py`), las cuatro
operaciones (`servidor/calculo.py`), el formato de números (`comun/formato.py`), el teclado y
display de la calculadora (`interfaz/gui.py`) y la base de las pruebas del protocolo. Los cambios
de cada uno están declarados en el §19.3 del reporte. Todo lo demás es original.
