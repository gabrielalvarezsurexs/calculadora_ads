# Roadmap — Calculadora ADS

Plan completo: [docs/PLAN.md](docs/PLAN.md). Notas internas: [CLAUDE.md](CLAUDE.md).

**Protocolo de cada sesión**
- Al iniciar: leer `ROADMAP.md`, `CLAUDE.md` y `docs/PLAN.md`; retomar en "Siguiente paso".
- Al cerrar: marcar casillas, actualizar "Estado actual" y anotar la sesión en el registro.
  Ninguna sesión cierra con código a medias sin anotarlo.
- Orden de fases estricto: 0 → A → B → C → D → E. Si una sesión rinde de más, se adelanta la
  siguiente sin saltarse el orden.

---

## Estado actual / siguiente paso

**Estado:** S6 terminada: **todas las fases (0 → E) completas.** `GUION_VIDEO.md` (15 escenas,
~16 min, comandos probados) y `docs/llenar_minutos.py` (copia los minutos del guion a la matriz
del reporte). Checklist final hecho de este lado; lo que queda es manual del usuario y está en
`ENTREGA.md`.

**Siguiente paso (usuario):** checklist previo del guion → grabar → minutos por escena →
`py docs/llenar_minutos.py` → portada → `py docs/md_a_docx.py` → commit/push (pedírselo al
asistente o hacerlo a mano) → entregar las tres ligas. Si se retoma con el asistente: ayudar con
esos pasos; no hay código pendiente.

**Notas de S6**
- El guion sigue el orden de la corrida verificada en S5 (no el de la matriz). La tabla
  "Matriz del reporte" del guion sí replica, en orden, las 35 filas del §2 que llevan video, y
  `docs/llenar_minutos.py` verifica § y requisito fila por fila antes de escribir.
- Los comandos de las escenas 6 y 7 cuentan todo `logs/`; por eso el checklist previo mueve las
  bitácoras del reporte a `logs_reporte_<fecha>/` (en `.gitignore`).
- Una captura (`PrintWindow`) de una ventana de nodo tapada por otras puede salir con la tabla de
  tráfico vieja (pasó una vez en S5; la ventana sí estaba bien). Si se recapturan figuras,
  revisarlas.

**Notas de S4/S5**
- **Pantalla del usuario: 2560×1600 físicos al 175 % (1463×914 lógicos).** Las geometrías de Tk
  están en unidades lógicas y cuadran con 1463×914.
- **Operar y capturar ventanas sin quitarle el foco al usuario** (él suele estar en VS Code; con
  la ventana en segundo plano, Windows bloquea `AppActivate` y `SendKeys` no sirve, e incluso
  podría teclear en VS Code):
  - Teclas: `PostMessage` a la primera ventana hija de la de Tk: primero `WM_SETFOCUS` (una app
    Tk nunca activada descarta el teclado), luego solo `WM_KEYDOWN`/`WM_KEYUP` (el
    `TranslateMessage` de Tk genera el carácter; mandar también `WM_CHAR` lo duplica). `*` y `/`
    van por el teclado numérico (`VK_MULTIPLY`, `VK_DIVIDE`): en el teclado español llevan Shift.
  - Capturas: `PrintWindow(hwnd, dc, 2)` desde un proceso DPI-aware; la ventana de Tk (no
    DPI-aware) sale a escala lógica en la esquina: recortar `ancho/1.75 × alto/1.75`.
  - **Excepción: el panel.** `PrintWindow` sobre la ventana del panel congela su hilo de Tk
    cuando el script de prueba corre dentro del proceso del panel. Para el panel: `-topmost`
    un par de segundos y `CopyFromScreen` de su rectángulo (sin tocar el foco).
- En Windows `terminate()` deja código de salida 1; el panel lo muestra como `tumbado` para no
  confundirlo con "puerto ocupado" (también 1).
- Los códigos de `config.CODIGOS_SILENCIOSOS` (`SRV_LAT`) no salen en consola, solo en archivo.
  Los `IGNORA` de células también van solo a archivo.
- Para el reporte:
  - Un respaldo puede registrar `RETIRADA` (vio el RES antes de cerrar su ventana de elección) en
    lugar de `RESPALDO` + `LIBERADO`. Ambos son correctos.
  - En la malla de 4, cada nodo distinto del de entrada ve cada mensaje 3 veces (1 FWD + 2 DUP)
    y el de entrada 1 FWD + 0 DUP (la `ruta` evita devolvérselo). Con 5 nodos: 1 FWD + 3 DUP.
  - La matriz del panel cuenta las células por el nodo con el que se LANZARON; tras un failover
    siguen en su fila aunque ya estén colgadas de otro nodo (la ventana del nodo dice la verdad).
  - Los tres bugs de S4 (abajo) son buen material para la sección de pruebas y fixes.

---

## S1 — Fase 0 + A1–A2

- [x] Carpeta `calculadora_ads/` + `git init`
- [x] `docs/PLAN.md`, `ROADMAP.md`, `CLAUDE.md`
- [x] Memoria del asistente con las preferencias del usuario
- [x] `pyproject.toml`, `.gitignore`, paquetes
- [x] `comun/`: protocolo, huella, codigos, mensajes, config, vistos, bitacora, formato
- [x] `nodo/nucleo.py` + `nodo/__main__.py --sin-ventana`
- [x] `sonda/`
- [x] Humo: 4 nodos headless forman la malla completa; sondas muestran FWD, DUP y TTL

**Criterio de salida:** 4 nodos headless forman la malla completa; las sondas muestran FWD, DUP y
TTL en las bitácoras.

## S2 — A3

- [x] `celula/base.py` (HOLA/BIENVENIDA, failover, dedup, filtrado por código)
- [x] `servidor/` (calculo, nucleo: acuse, cola, elección HRW, relevo, latidos)
- [x] `interfaz/nucleo.py` (quórum por intento, reintentos, disponibilidad por latidos)
- [x] Humo: script en scratch resuelve las 4 operaciones con un solo RES; failover al tumbar un nodo

## S3 — A4–A5

- [x] `nodo/gui.py`
- [x] `interfaz/gui.py`
- [x] `panel/` (matriz, configuración mínima, lista de procesos, bitácora en vivo)
- [x] Humo: con el panel, la configuración mínima corre con ventanas y se opera a mano

## S4 — B + C

- [x] Suite unitaria (§12 del plan)
- [x] Suite de integración: `test_malla`, `test_broadcast`, `test_flujo`
- [x] Verificación en vivo (§14 del plan) + capturas a 1463×914
- [x] Fixes; repetir hasta que quede limpio

## S5 — D

- [x] README.md, ENTREGA.md, CLAUDE.md completo
- [x] REPORTE_TECNICO.md con bitácoras reales
- [x] Conversión a `.docx`

## S6 — E

- [x] GUION_VIDEO.md amarrado a la tabla §10 del plan
- [x] Checklist final

---

## Registro de sesiones

| Fecha | Sesión | Qué se hizo | Pendiente | Problemas abiertos |
|---|---|---|---|---|
| 2026-10-10 | S1 | Fase 0 completa. `comun/*`, `nodo/nucleo.py`, `nodo/__main__.py`, `sonda/`. Humo (scripts en scratch, no versionados): 4 nodos con semillas en cadena → 3 vecinos cada uno, marcados simultáneos resueltos por la regla de enlace duplicado (se registran como `DUPLICADO`); sonda normal → FWD en 4 nodos + 2 DUP en cada uno; `--ttl 1` → TTL en el primer nodo; `--ttl 0` → no se procesa; `--repetir 3` → 1 FWD + 2 DUP; `--id` en otro nodo → DUP; puerto ocupado → código 1; nodo tumbado → DESCONEXION + un solo INALCANZABLE; relanzado en el mismo puerto → vuelve a la malla. `ruff` limpio. | S2 completo. | (1) Durante un marcado simultáneo, los datos que viajen por el enlace que la regla descarta se pierden (solo en el arranque; los reintentos de la GUI lo cubren). (2) Enlaces medio abiertos no se detectan (ya está en trabajo futuro). |
| 2026-10-10 | S2 | `celula/base.py`, `servidor/{calculo,nucleo,__main__}.py`, `interfaz/{nucleo,__main__}.py`. Humo (`humo_s2.py` en scratch: 4 nodos + 16 servidores como procesos, 4 GUIs + célula espía en proceso): 4 operaciones simultáneas, una por GUI, + 1÷0 → resueltas, 4/2 acuses, **exactamente 1 RES** cada una según el espía; las demás GUIs registran IGNORA; tumbar el Nodo 1 → GUI-1 y sus 4 servidores hacen FAILOVER a Nodo 2 en ~3 s, sin caducar ninguna célula, y las operaciones siguen; SUM con `--retardo-ms 4000` como titular → RELEVO 1 de otra célula a ~2 s + SUPRIMIDA en la lenta, 1 solo RES. `ruff` limpio. **Fixes durante el humo:** (a) en Windows `connect()` a un puerto cerrado tarda ~2 s, lo que llevaba el failover a ~6 s y caducaba todas las células en la GUI → reintentos al mismo nodo con `REINTENTO_TIMEOUT` (0.5 s, constante nueva en `config`); (b) la GUI no caduca células mientras ella misma está sin enlace y, al reconectarse, les da un plazo completo. | S3 completo. | Ninguno nuevo. |
| 2026-10-10 | S3 | `nodo/gui.py` (+ `eventos` en `nodo/__main__.py`), `interfaz/gui.py`, `panel/{procesos,gui,__main__}.py`. Humo (`humo_s3.py`/`humo_s3b.py` en scratch; el panel se maneja con `after`, las GUIs con `SendKeys`, capturas DPI-aware): configuración mínima → 4 ventanas de nodo con "Vecinos: 3" y "Células: 5 (1 GUI + 4 servidores)", tráfico FWD/DUP con ruta y destinos; GUIs habilitan los 4 operadores con "vivas: 4"; tecleado 7+5 → 12, 6×7 → 42, 1÷0 → ERROR "división entre cero", cada una con mini log SOLICITUD/ACUSE/QUÓRUM/RESULTADO; tumbar el Nodo 4 desde el panel → GUI-4 "failover → Nodo 1" sin perder operadores y el Nodo 1 muestra "Células: 10"; tumbar SUM-N2 → matriz en "○ 0". `ruff` limpio. Ajustes tras ver las capturas: estado `tumbado` en el panel, ajuste de línea en "Mis operaciones", barra de desplazamiento en la tabla de células. | S4 completo. | Ninguno nuevo. |
| 2026-10-11 | S4 | **Suite** (`tests/`): unitarias `test_protocolo`, `test_enlace`, `test_huella`, `test_mensajes`, `test_vistos`, `test_calculo`, `test_formato`, `test_bitacora`; integración en proceso con puertos efímeros y tiempos acortados (`tests/apoyo.py`: `Sistema`, `Registro` en memoria con ganchos, `Receptor`, `Espia`): `test_malla` (cadena de semillas → malla completa verificando que ambos extremos son la MISMA conexión TCP, marcado simultáneo ×5, autoconexión vía alias `localhost`, 5º nodo, nodo tumbado, nodo que vuelve), `test_broadcast` (con la sonda real: exactamente una vez por célula, DUP, ruta/TTL, `--ttl 1`, `--ttl 0`, TTL recortado, `--repetir 3`, `--id`, basura y datos sin HOLA), `test_flujo` (4 nodos + 16 servidores + 4 GUIs + espía: 4 operaciones con 1 TITULAR/3 liberados/1 RES, ÷0, titular lenta → relevo + suprimida, titular muerta tras acusar → relevo, 3 SUM tumbadas → deshabilitada → una nueva → habilitada, nodo tumbado → failover sin CADUCA con la caducidad real, regla ≤ k, ronda superada, REQ desordenado, ACK antes del REQ con ranking verificado, y reglas de la GUI sin red). 106 pruebas, ~83 s, 3 corridas seguidas en verde; `ruff` limpio. **Bugs encontrados y corregidos:** (1) un REQ del intento k que llegaba DESPUÉS del k+1 (desorden en la malla) generaba un segundo RES (visto en 1 de 6 operaciones con un diagnóstico) → el servidor marca SUPERADA la ronda si ya conoce un intento posterior, sin acusar ni encolar; (2) al formarse la malla, 1 de cada ~25 veces un enlace sobrante se cerraba sin RECHAZO y el par lo registraba como `DESCONEXION` (caída falsa) → `_registrar_saliente` ahora manda `RECHAZO(duplicado)` (0 en 60 formaciones); (3) el reemplazo de un enlace duplicado no dejaba rastro y la ventana mostraba dos `CONEXION` seguidas → se registra `DUPLICADO`. Ajuste visual: columnas evento/código de la ventana del nodo (cortaban `SONDA_PRUEBA` y `DESCONEXION`). **Verificación en vivo** (panel real, 24 procesos, teclas por `PostMessage` y capturas por `PrintWindow` sin quitarle el foco al usuario; ver notas): 7+5, 10−4, 6×7, 7÷2, 1÷0 → por operación 4 ACUSE, 1 TITULAR, 3 LIBERADO, 1 RES, las otras 3 GUIs con IGNORA y en cada nodo 1 FWD + 2 DUP (0 DUP en el de entrada); Nodo 1 tumbado → sus 5 células en FAILOVER a Nodo 2 en ~3.0 s, sin CADUCA, y 9×9 sigue resolviendo; 3 DIV tumbadas → DESHABILITADA en las 4 GUIs y "DIV no disponible" al pulsar ÷; DIV-N2b → HABILITADA y 8÷2 = 4; SUM-N3b con `--retardo-ms 4000` titular en la 6ª operación → RELEVO 1 de SUM-N2 a 2.0 s y SUPRIMIDA a 4.0 s, 1 solo RES; sondas: `--ttl 1` solo en Nodo 2 (FWD+TTL), `--repetir 3` 1 FWD + 2 DUP, `--id` en Nodo 3 → DUP; Nodo 1 relanzado + "+ Nodo" → Nodo 5 con 4 vecinos y 2+2 con 1 FWD + 3 DUP por nodo; panel cerrado con "No" → 24/24 vivos, bitácoras creciendo y 2+2 resuelto sin panel. Sin `ERROR`, `Traceback`, `PERDIDO`, `DROP` ni `LENTO` en ninguna bitácora. | S5 completo. | (1) `PrintWindow` sobre el panel congela su Tk dentro del mismo proceso (solo afecta a las herramientas de captura). (2) Los de S1 siguen: enlaces medio abiertos no se detectan (trabajo futuro). |
| 2026-10-11 | S5 | **Bitácoras regeneradas** con el código final (el log `DUPLICADO` del nodo cambió después de la corrida de S4): misma corrida en vivo con el panel real (`humo_s5.py`/`humo_s5b.py` en scratch), mismos resultados que S4 — por operación 4 ACUSE / 1 TITULAR / 3 LIBERADO / 1 RES, failover en ~3.0 s sin CADUCA (los 3 CADUCA por GUI son las 3 DIV tumbadas, como debe ser), relevo + suprimida con `SUM-N3b` en la 4ª operación, sondas, Nodo 5, 24/24 vivos sin panel, cero errores. **Documentos:** `README.md`, `ENTREGA.md`, `CLAUDE.md` completo, `REPORTE_TECNICO.md` (Partes I/II/III, matriz §1–§15 con columna Video, 10 pasos del §12 con bitácoras reales, 3 diagramas de tiempo alineados al milisegundo de la corrida, las 6 capas contra respuestas duplicadas, los 3 bugs de S4, diferencias con la clase, limitaciones, glosario, constantes, APA; DOIs de Mori, Thaler y Demers no verificables, se citan sin DOI). 8 capturas en `docs/capturas/` (recortados los bordes invisibles de Windows 11). **Conversor** `docs/md_a_docx.py` (stdlib; no hay pandoc ni LibreOffice) → `.docx` de 38 páginas, abierto y exportado a PDF con Word por COM y revisado página por página; ajustes tras la revisión: tabla de portada sin encabezado vacío, anchos mínimos de columna, código a 7.5 pt, tope de altura de imágenes, encabezados de tabla no huérfanos. `ruff` limpio. | S6 completo. | Ninguno nuevo. |
| 2026-10-11 | S6 | **`GUION_VIDEO.md`**: checklist previo (procesos vivos = 0, bitácoras del reporte a `logs_reporte_<fecha>/`, pruebas), grabador de pantalla completa (la Game Bar graba una sola ventana), mapa real de dónde quedan las ventanas a 1463×914, 15 escenas con qué se ve / qué hacer / qué decir (incluidas las dos notas frente a la clase en las escenas 7 y 11), tabla "si algo se rompe", limpieza de procesos y tablas de minutos. Comandos probados antes de escribirlos: conteo de `RES` por operación y papeles de una operación (sobre las bitácoras de S5: 12 operaciones, Count = 1 cada una), sondas `--ttl 1`/`--repetir 3`/`--id $id` con captura del id en PowerShell (4 nodos headless desde una copia en scratch, sin tocar `logs/`), limpieza de procesos (`py.exe` + `python.exe`). **`docs/llenar_minutos.py`** (stdlib): minutos por escena del guion → columna "Video" del §2, verificando § y requisito de las 35 filas; probado sobre copias: cambia exactamente 35 celdas, idempotente, respeta minutos puestos a mano, rechaza formato inválido y no escribe si falta una escena. Corrección en el reporte (§7.2) y en el guion: el REQ llega a las otras **19** células, no a 20 (el nodo no se lo devuelve a la GUI que lo envió). `GUION_VIDEO.md` agregado al README y al Anexo C; `.gitignore` con `logs_*/`; ENTREGA con pasos nuevos y checklist final. **Checklist final:** 106 pruebas en verde (82.7 s), `ruff` limpio, 31 ligas relativas sin rotas, `.docx` regenerado (38 páginas, abre en Word). No se hizo un ensayo con ventanas para no tomar la pantalla del usuario: todas las escenas son las de la corrida de S5. | Pasos manuales del usuario (ENTREGA.md). | Ninguno nuevo. |
