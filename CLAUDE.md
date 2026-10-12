# Calculadora ADS — notas internas

Proyecto del segundo parcial de Cómputo Distribuido: la calculadora del primer parcial pasada a una
arquitectura ADS (Campo de Datos de nodos en malla, células GUI y servidor, todo por broadcast con
Códigos de Contenido). Plan completo en `docs/PLAN.md`; avance por sesiones en `ROADMAP.md`.

## Al iniciar una sesión
Leer `ROADMAP.md` → "Estado actual / siguiente paso", y la sección del plan que toque.

## Decisiones (no reabrir; detalle en docs/PLAN.md §0.1)
- Python 3 (`py`), **solo librería estándar**. Sin Java a propósito.
- Fases en orden estricto: 0 → A código → B pruebas → C fixes → D reporte → E guion.
- Nodos "bobos": aceptan conexiones, inundan, evitan ciclos. Nunca leen `cuerpo`.
- Todo dato viaja por broadcast; cada célula filtra por código.
- Todo tiene hash SHA-256 (nodos, células, mensajes, operaciones). Cada entidad genera el suyo.
- Servidor: acusa al recibir, encola, elección HRW entre los que acusaron; una titular responde,
  las demás son respaldos escalonados.
- Disponibilidad por latidos (`SRV_LAT`); la GUI deshabilita el operador si vivas < mínimo.
- Failover de células a otro nodo de la malla.
- El PDF manda sobre lo visto en clase; las diferencias se mencionan breve y respetuosamente.
- Commits solo cuando el usuario lo pida.

## Cómo correr (desde esta carpeta)
```
py -m nodo --puerto 5001 --nombre "Nodo 1" [--semillas 127.0.0.1:5002] [--sin-ventana]
py -m servidor --servicio SUM --nodo 127.0.0.1:5001 [--nombre SUM-N1] [--retardo-ms 0]
py -m interfaz --nodo 127.0.0.1:5001 [--nombre GUI-1] [--acuses-min 2] [--geometria WxH+X+Y]
py -m sonda --nodo 127.0.0.1:5001 [--ttl 8] [--id <hash>] [--repetir N]
py -m unittest discover -s tests -t .
py -m panel        # demo: "Levantar configuración mínima"
py docs/md_a_docx.py   # REPORTE_TECNICO.md -> Reporte_Tecnico_Calculadora_ADS.docx
py docs/llenar_minutos.py [--revisar]   # minutos de GUION_VIDEO.md -> columna "Video" del reporte
```

## Reglas de código
1. `nucleo.py` nunca importa Tkinter; eventos por `queue.Queue` + `after(100)`.
2. Constantes como `config.X` al usarlas, nunca `from comun.config import X`.
3. Estado compartido entre hilos protegido por el lock del objeto dueño.
4. Ningún hilo de red muere por excepción: se registra `ERROR` y se sigue.
5. Al arrancar: `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`.

## Dónde está cada cosa
- `comun/` — transporte NDJSON + `Enlace`, hashes, códigos, sobre de mensajes, config, registro de
  vistos, bitácora, formato de números.
- `nodo/` — nodo del Campo de Datos (`nucleo.py` headless, `gui.py` ventana).
- `sonda/` — CLI de demo para inyectar mensajes con TTL/id elegidos (fuera del sistema).
- `celula/base.py` — célula base (ACP): conexión, BIENVENIDA/PARES, failover, dedup propio,
  `publicar()`; las subclases implementan `procesar()`, `al_conectar()`, `al_desconectar()`.
- `servidor/` — `calculo.py` (función pura) y `nucleo.py` (rondas, acuse inmediato, cola,
  elección HRW, respaldos con `Programador`, relevo, doble revisión, latidos).
- `interfaz/nucleo.py` — GUI sin Tkinter: operaciones, quórum por intento, RES retenido,
  reintentos, disponibilidad por latidos; empuja eventos a una cola. `interfaz/gui.py` la ventana.
- `nodo/gui.py` — tablas de vecinos y células, contadores y tráfico en vivo.
- `panel/` — herramienta de demo FUERA del sistema: `procesos.py` (lanzar/vigilar/tumbar, sin
  Tk) y `gui.py` (matriz, configuración mínima, procesos, bitácora en vivo).
- `tests/` — unitarias por módulo de `comun/` y `servidor/calculo.py`; integración en proceso
  (`test_malla`, `test_broadcast`, `test_flujo`) con `tests/apoyo.py`: `Sistema` (nodos y
  células con puertos efímeros), `Registro` (bitácora en memoria con ganchos), `Receptor`,
  `Espia` (cuenta ACK/RES por operación e inyecta mensajes) y `acortar` (parcha `config`).
  `RELEVO` nunca baja de 1 s en pruebas.
- Pantalla del usuario: 1463×914 lógicos (2560×1600 al 175 %). Para operar/capturar ventanas sin
  quitarle el foco: ver notas del ROADMAP (PostMessage + PrintWindow).
- `logs/` — bitácoras `<nombre>-<hash8>.log` (ignoradas por git).

## Documentación (entregables)
- `README.md` — puerta de entrada del repo. `ENTREGA.md` — estado de los 3 entregables, lo que
  hace el usuario a mano y el checklist final.
- `GUION_VIDEO.md` — 15 escenas (~16 min) en el orden de la corrida verificada, con comandos de
  PowerShell probados (conteo de `RES` por operación, papeles de una operación, sondas con `$id`,
  limpieza de procesos). Al final, "Minutos por escena" y "Matriz del reporte": esta última
  replica, en el mismo orden, las filas del §2 del reporte que llevan video. Si se agrega o quita
  una fila de la matriz, hay que reflejarlo ahí o `docs/llenar_minutos.py` se niega a escribir.
- `REPORTE_TECNICO.md` — el reporte (Partes I/II/III, matriz de trazabilidad con columna "Video"
  en `<mm:ss>`, figuras de `docs/capturas/`). Las bitácoras citadas son de la corrida del
  2026-10-11 19:09–19:12 con el código final; si se cambia código que altere una línea citada,
  hay que regenerarlas y actualizar el reporte. El checklist del guion mueve esas bitácoras de
  `logs/` a `logs_reporte_<fecha>/` (ignorada por git) antes de grabar.
- `Reporte_Tecnico_Calculadora_ADS.docx` — se genera, no se edita a mano:
  `py docs/md_a_docx.py` (stdlib; entiende solo el subconjunto de Markdown que usa el reporte:
  encabezados, párrafos, listas de 2 niveles, tablas, bloques de código, citas, `---`, imágenes
  PNG en su propio renglón). Los bloques de código salen a 7.5 pt: líneas de ≤ 110 caracteres.
- Para revisar el `.docx`: Word por COM (`Documents.Open` + `SaveAs2(pdf, 17)`) y renderizar el
  PDF con la API `Windows.Data.Pdf` (no hay pandoc, LibreOffice ni pdftoppm en esta máquina).
- Portada: marcadores `<NOMBRE COMPLETO>`, `<MATRÍCULA>`, `<GRUPO>`, `<LIGA AL REPOSITORIO>`,
  `<LIGA AL VIDEO>`; los llena el usuario.
