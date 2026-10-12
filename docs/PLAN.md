# Plan — Calculadora ADS (Proyecto del Segundo Parcial, Cómputo Distribuido)

> Plan **autocontenido**: con este documento, una sesión nueva puede implementar el proyecto sin
> la conversación previa. En la Fase 0 se copia al repo como `docs/PLAN.md`.

---

## 0. Contexto

**Antecedente.** El primer parcial vive en
`c:\SCHOOL\COMPUTO_DISTRIBUIDO\proyecto_computo_distribuido\` (Python): calculadora
cliente/servidor de 3 capas con **middleware central** en :7000, consenso entre servidores,
PostgreSQL/SQLite y Tkinter.

**Enunciado nuevo.** `Instrucciones_Proyecto_Segundo_Parcial_ADS.pdf` (6/oct/2026) pide pasar esa
calculadora a una **arquitectura ADS**:

- **Campo de Datos** de 4 nodos en **malla completa**.
- Por nodo: **1 célula GUI + 4 células servidor** (+, −, ×, ÷); 20 células en total.
- Comunicación **solo por broadcast** con **Códigos de Contenido** (`SUM_REQ`/`SUM_RES`, etc.).
- Prevención de ciclos y de duplicados.
- **Ningún punto único de falla** (§15).
- Protocolo **escalable**: N nodos y N células sin cambiar el código.

**Entregables** (§2): reporte técnico, video con audio y liga al código (célula cliente, célula
servidor y nodo). Las secciones a las que el usuario pidió poner más cuidado son **§10
(protocolos)**, **§11 (ciclos y duplicados)** y **§14 (evidencias)**.

**Por qué se empieza de cero.** El middleware del primer parcial es exactamente lo que el §15
prohíbe, y su "todos los servidores calculan" contradice el §9. Del primer parcial solo se
reutilizan piezas puntuales (ver §13).

### 0.1 Decisiones tomadas con el usuario (no reabrir)

| Tema | Decisión |
|---|---|
| Lenguaje | **Python** (3.14 instalado; se ejecuta con `py`), **solo librería estándar**. Se renuncia **a propósito** a los puntos extra de Java. |
| Carpeta | Nueva: `c:\SCHOOL\COMPUTO_DISTRIBUIDO\calculadora_ads\`, con **git propio**. El usuario crea el repo en GitHub y hace push. El primer parcial no se toca. |
| Orden de trabajo | **Por fases, estrictamente**: 0 preparación → A código → B pruebas → C fixes → D reporte → E guion. |
| Nodos | **"Bobos"**: solo aceptan conexiones, hacen broadcast y evitan ciclos. Nunca leen el `cuerpo` ni conocen el catálogo de códigos. |
| Comunicación | **TODO por broadcast.** Cada célula decide por Código de Contenido si procesa o ignora. |
| Hashes | **Todo** tiene un hash SHA-256 único: nodos, células, mensajes, operaciones y acuses. Cada entidad genera el suyo al presentarse. |
| Acuses | La célula servidor **acusa en cuanto recibe** la solicitud y luego la mete en su **cola**. Cada operación tiene un **mínimo de acuses configurable** (por defecto 2). |
| Disponibilidad | **Latidos por broadcast.** En clase se vio "solo por acuses"; el usuario prefirió latidos y lo **explica en el video** (va en el guion y en el reporte). |
| Operación deshabilitada | Si las células vivas de un servicio son menos que su mínimo de acuses, la GUI **deshabilita** ese operador y lo anota en su mini log. |
| Anti-duplicados (§9/§11) | **Elección por hash entre las células que acusaron**: una sola titular responde y las demás quedan como respaldos escalonados. En clase se dijo "todas responden y la GUI toma la primera"; **el PDF manda**, porque el §9 pide *evitar* las respuestas no deseadas. Se menciona en el reporte y en el video, **breve y respetuosamente**. |
| Otras GUIs | Una GUI **no ve** las solicitudes de las otras: le llegan por broadcast, pero las ignora por código y por id de operación. |
| Reintentos | Cada operación tiene un **id propio** (hash). El reintento reusa ese id con `intento+1` y lleva un **id de mensaje nuevo**. |
| Failover | **Sí.** Si muere el nodo de una célula, la célula se pasa sola a otro nodo de la malla. |
| Demo | **Panel de despliegue**: herramienta aparte que **no** forma parte del sistema. Nodos y GUIs abren su ventana; los servidores corren sin ventana y su bitácora se ve en el panel. Pantalla del usuario: 1463×914. |
| Foliado | **No se implementa**: no lo pide el PDF y queda para la entrega final. Solo se anota como trabajo futuro. |
| Células que levantan células | **No** (entrega final). Por ahora las células nuevas se levantan a mano, desde el panel o la CLI, y se muestra cómo se integran en vivo. |
| Reporte y guion | Mismo estilo que el primer parcial: Markdown con Partes I/II/III, matriz de trazabilidad con el minuto del video, diagramas, tablas y APA. Al final, `.docx`. |
| Sesiones | El trabajo se reparte en **varias sesiones** guiadas por `ROADMAP.md` (§17). |

---

## 1. Arquitectura

```
   GUI-1 SUM-N1 SUB-N1 MUL-N1 DIV-N1            GUI-2 SUM-N2 SUB-N2 MUL-N2 DIV-N2
          \    \    |    /    /                        \    \   |   /    /
           [ NODO 1 :5001 ] ═══════════════════════ [ NODO 2 :5002 ]
                 ║        ╲\                     /╱        ║
                 ║          ╲\                 /╱          ║      malla completa:
                 ║            ═════════╳═══════            ║      cada nodo ↔ los otros 3
                 ║          /╱                 ╲\          ║
           [ NODO 3 :5003 ] ═══════════════════════ [ NODO 4 :5004 ]
          /    /    |    \    \                        /    /   |   \    \
   GUI-3 SUM-N3 SUB-N3 MUL-N3 DIV-N3            GUI-4 SUM-N4 SUB-N4 MUL-N4 DIV-N4
```

| Componente | Paquete | Rol |
|---|---|---|
| Nodo del Campo de Datos | `nodo/` | Acepta conexiones de nodos y células, identifica el tipo de entidad, forma la malla por gossip e inunda con supresión de duplicados y TTL. No interpreta contenido. |
| Célula base | `celula/base.py` | Lo común a toda célula, equivalente al **ACP** de ADS: conectar, presentarse, failover, deduplicar y filtrar por código. |
| Célula servidor | `servidor/` | **Un** servicio por instancia (`--servicio SUM|SUB|MUL|DIV`). Acusa, encola, participa en la elección, calcula y responde, y emite latidos. Equivale al **ASM**. |
| Célula GUI | `interfaz/` | Calculadora Tkinter: solicita, cuenta acuses, reintenta, muestra el resultado y habilita o deshabilita operaciones según los latidos. |
| Panel de despliegue | `panel/` | Herramienta de demo que lanza y tumba procesos. **Fuera del sistema.** |
| Sonda | `sonda/` | CLI de demo que inyecta mensajes con TTL o id elegidos (§11). **Fuera del sistema.** |

El vocabulario ACP/ASM viene de la Práctica 3 del curso y se usa en el reporte.

---

## 2. Estructura del proyecto

```
calculadora_ads/
  pyproject.toml      # requires-python >=3.12, sin dependencias
  .gitignore          # logs/, __pycache__/, .venv/, *.pyc
  ROADMAP.md          # roadmap por sesiones + estado actual (§17)
  CLAUDE.md           # notas internas: decisiones, cómo correr, dónde está cada cosa
  docs/PLAN.md        # copia de este plan
  README.md  REPORTE_TECNICO.md  GUION_VIDEO.md  ENTREGA.md      # fases D y E
  comun/
    protocolo.py      # NDJSON: enviar() + lector tolerante a líneas inválidas + Enlace (cola de escritura)
    huella.py         # hashes únicos y ranking de elección
    codigos.py        # catálogo de Códigos de Contenido, servicios, símbolos
    mensajes.py       # sobre (envelope), constructores, validación estructural
    config.py         # TODAS las constantes de tiempo, TTL y tamaños
    vistos.py         # RegistroVistos: registro TEMPORAL de ids
    bitacora.py       # consola (segura ante pipes rotos) + archivo + callback para la GUI
    formato.py        # números y operaciones legibles (adaptado del 1er parcial)
  nodo/      __main__.py  nucleo.py  gui.py
  celula/    base.py
  servidor/  __main__.py  nucleo.py  calculo.py
  interfaz/  __main__.py  nucleo.py  gui.py
  panel/     __main__.py  gui.py  procesos.py
  sonda/     __main__.py
  tests/     test_*.py    # unittest, sin dependencias
  logs/                   # bitácoras (ignoradas por git)
```

**Reglas de código:**
1. Los `nucleo.py` **no importan Tkinter**. Empujan eventos a una `queue.Queue` que la GUI vacía con
   `after(100)`. Tkinter no es thread-safe, y así las pruebas corren sin ventanas.
2. Las constantes se leen como `config.X` en el momento de usarse, **nunca**
   `from comun.config import X`, para que las pruebas puedan acortar los tiempos con `mock.patch`.
3. Todo estado compartido entre hilos va protegido por un `threading.Lock` del objeto dueño.
4. Ningún hilo de red muere por una excepción: se registra `ERROR` y se sigue.
5. Al arrancar: `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`.

**CLI** (siempre desde la raíz `calculadora_ads/`):
```
py -m panel
py -m nodo --puerto 5001 --nombre "Nodo 1" [--host 127.0.0.1] [--semillas 127.0.0.1:5002,...] [--sin-ventana] [--geometria WxH+X+Y]
py -m servidor --servicio SUM --nodo 127.0.0.1:5001 [--nombre SUM-N1] [--retardo-ms 0]
py -m interfaz --nodo 127.0.0.1:5001 [--nombre GUI-1] [--acuses-min 2] [--geometria WxH+X+Y]
py -m sonda --nodo 127.0.0.1:5001 [--ttl 8] [--id <hash>] [--repetir N]
```
`--host` vale **127.0.0.1 por defecto** para que el firewall de Windows no abra su diálogo en plena
demo. Para LAN se pasa `--host 0.0.0.0`.

---

## 3. Identificadores (hashes) — `comun/huella.py`

```python
def generar(tipo: str, *datos) -> str:
    # sha256("tipo|datos...|hostname|pid|time_ns|contador_del_proceso|secrets.token_hex(16)")
    return hexdigest                     # 64 caracteres hex
def de_entidad(entidad, nombre, servicio=None) -> str
def de_mensaje(origen) -> str
def de_operacion(interfaz, servicio, a, b) -> str
def corto(h) -> str: return h[:8]        # solo para mostrar
def prioridad(celula, id_operacion, intento) -> str:   # ranking HRW, determinista
    return sha256(f"{celula}|{id_operacion}|{intento}").hexdigest()
```
- **Unicidad**: 128 bits aleatorios, reloj en ns, contador por proceso, pid y host. La probabilidad
  de colisión es ~2⁻¹²⁸, y el contador garantiza unicidad dentro del proceso aunque el reloj se
  repita.
- **Cada entidad genera su hash al arrancar** y lo presenta en el `HOLA`. El nodo no asigna
  identidades. El hash es por proceso: si se reinicia, la entidad es "nueva".
- Los nombres ("Nodo 1", "SUM-N3", "GUI-2") son **solo etiquetas** para mostrar; la identidad es el
  hash.
- Ranking: se ordena por `(prioridad, hash_célula)`. El empate es imposible en la práctica y aun
  así queda definido.

---

## 4. Protocolos

### 4.1 Transporte — `comun/protocolo.py`
- TCP con **NDJSON** (un JSON por línea, UTF-8). `enviar()` se adapta del primer parcial con
  `json.dumps(..., ensure_ascii=False, allow_nan=False)`.
- **Lector tolerante**. El `leer_mensajes()` del primer parcial hace `json.loads` *dentro* del
  generador, así que una línea inválida lanza y **termina el generador**, es decir, cierra el
  enlace. El nuevo lector entrega cada línea con un `try` propio, descarta la inválida
  (`DROP: no es JSON`) y sigue. Si se acumulan más de `MAX_LINEA` (64 KiB) sin `\n`, descarta el
  buffer.
- **`Enlace`** envuelve un socket con una **cola de salida y un hilo escritor propio**. Quien
  difunde solo encola bytes y nunca se bloquea por un par lento o colgado. Si la cola rebasa
  `COLA_ENLACE_MAX` (5 000), el enlace se da por muerto: se cierra y se registra `LENTO`.
  Expone `enviar(dict)`, `enviar_bytes(b)`, `cerrar()`, `vivo`, `iniciador` (yo / él),
  `entidad`, `hash`, `nombre` y `endpoint`.

### 4.2 Protocolo de conexión (§10.1)
Son mensajes de control: van **por enlace**, **nunca se retransmiten** y llevan `"ctrl"` en lugar
de `"codigo"`.

| ctrl | Dirección | Campos | Propósito |
|---|---|---|---|
| `HOLA` | entidad → nodo | `entidad` (NODO, INTERFAZ, SERVIDOR o SONDA), `hash`, `nombre`, `servicio` (o null), `escucha` (puerto; solo nodos), `version` (1) | Presentación: **identifica el tipo de entidad**. |
| `BIENVENIDA` | nodo → entidad | `hash`, `nombre`, `nodos` (endpoints conocidos) | Confirma el registro. Le da la lista para el failover (células) y para el gossip (nodos). |
| `PARES` | nodo → todos sus enlaces | `nodos` | Gossip: se manda cada vez que crece el conjunto de nodos conocidos. |
| `RECHAZO` | nodo → entidad | `motivo` (`duplicado`, `autoconexion`, `version`, `invalido`), `hash` | Se manda y se cierra el enlace. |

**Reglas del nodo**
1. **Registro de entidades.** Una conexión entrante debe mandar un `HOLA` válido en
   `HOLA_TIMEOUT` (5 s) o se cierra. Mientras no se presente, sus datos se descartan. Si la entidad
   es NODO va a `vecinos[hash]`; si es INTERFAZ, SERVIDOR o SONDA va a `celulas[hash]`. Ambas
   tablas se ven en la ventana del nodo: es el **control de conexiones activas**.
2. **Célula repetida** (mismo hash con un enlace previo que aún no se detecta como muerto): gana
   el enlace nuevo y el viejo se cierra.
3. **Descubrimiento descentralizado.**
   - Al recibir el HOLA de un nodo, su endpoint se forma con la **IP real del socket** y el puerto
     `escucha`. Al marcar, el endpoint es el que se marcó.
   - `conocidos` es el conjunto de endpoints de nodos, y `alias[endpoint] = hash` se aprende del
     HOLA, la BIENVENIDA o el RECHAZO.
   - Un **supervisor** corre cada 2 s. Por cada endpoint conocido que no sea propio, no esté
     cubierto (su alias no está en `vecinos`) y no tenga un marcador en curso, lanza un marcador con
     backoff de 1 a 8 s.
   - **Basta conocer un nodo cualquiera**: BIENVENIDA y PARES hacen que todos acaben conectados con
     todos. Resultado: **malla completa con N nodos**.
4. **Regla de enlace duplicado**, aplicada al registrar un vecino cuyo hash ya tiene enlace.
   Sea `preferido = min(mi_hash, hash_par)`, el nodo que "debe" iniciar:
   - el nuevo lo inició `preferido` y el existente no → se queda el **nuevo** y se cierra el
     existente;
   - en cualquier otro caso (incluido que ambos los haya iniciado el mismo lado por endpoints
     alias) → se queda el **existente** y el nuevo recibe `RECHAZO(duplicado)`.

   Ambos lados aplican la misma función, que solo depende de los hashes y del iniciador de cada
   enlace, así que convergen. El marcador rechazado anota el alias y se detiene.
5. **Autoconexión** (`HOLA.hash == mi_hash`): `RECHAZO(autoconexion)` y el endpoint se marca como
   propio para no volver a marcarlo.
6. **Puerto ocupado**: el nodo termina con un mensaje claro y código 1 (el panel lo muestra).
7. Los endpoints muertos se reintentan con backoff, y solo se registra el **cambio** de estado
   (no cada intento).
8. `PARES` converge porque los conjuntos solo crecen y son finitos.

**Reglas de la célula** (`celula/base.py`)
- Conecta a `--nodo`, manda `HOLA` y espera `BIENVENIDA` (3 s). Hasta entonces **no publica nada**.
- Guarda `nodo_actual` (hash, nombre y endpoint) y `candidatos` (la lista `nodos`, que actualiza con
  cada `PARES`).
- **Failover**: si se cae el enlace, reintenta 2 veces con su nodo (1 s entre intentos) y luego
  rota por los demás candidatos (round-robin). Si ningún nodo responde en una vuelta completa,
  espera con backoff (máx. 8 s) y empieza otra. Registra `FAILOVER → Nodo k`. Si su nodo original
  revive, **no** regresa a él, para no oscilar.
- **Publicar sin conexión** devuelve `None` y se registra. Ese mensaje se pierde, y lo absorben los
  reintentos de la GUI (§5).

### 4.3 Protocolo de comunicación (§10.2) — mensajes de datos, **siempre broadcast**

**Sobre** (envelope). El nodo solo usa `id`, `ttl` y `ruta`; `codigo`, `origen` y `nombre_origen`
los lee únicamente para mostrarlos.
```json
{
  "id": "<sha256>",              // identificador único del mensaje
  "codigo": "SUM_REQ",           // Código de Contenido
  "origen": "<hash célula>",     // célula que originó el mensaje
  "tipo_origen": "INTERFAZ",
  "nombre_origen": "GUI-1",
  "ts": 1760100000.123,          // epoch del origen (solo informativo)
  "ttl": 8,                      // nodos que aún pueden procesarlo
  "ruta": ["<hash nodo>", ...],  // nodos que ya lo procesaron, en orden
  "cuerpo": { ... }
}
```

**Códigos de Contenido** (`comun/codigos.py`). REQ y RES son los del PDF §7; ACK y LAT se agregan
por el modelo de acuses de la clase y por los latidos.

| Servicio | Solicitud | Acuse | Respuesta | Símbolo |
|---|---|---|---|---|
| Suma | `SUM_REQ` | `SUM_ACK` | `SUM_RES` | + |
| Resta | `SUB_REQ` | `SUB_ACK` | `SUB_RES` | − |
| Multiplicación | `MUL_REQ` | `MUL_ACK` | `MUL_RES` | × |
| División | `DIV_REQ` | `DIV_ACK` | `DIV_RES` | ÷ |

| Código | Cuerpo |
|---|---|
| `*_REQ` | `id_operacion`, `intento`, `a`, `b` |
| `*_ACK` | `id_operacion`, `id_solicitud` (id del REQ acusado), `intento`, `en_cola` |
| `*_RES` | `id_operacion`, `id_solicitud`, `intento`, `resultado` (o null), `error` (o null), `rol` (`"titular"` o `"relevo k"`), `ms` |
| `SRV_LAT` | `servicio`, `en_cola`, `atendidas`, `nodo` (hash), `nodo_nombre` |
| `SONDA_PRUEBA` | `nota` (solo para la sonda; ninguna célula lo procesa) |

- La respuesta lleva **id de mensaje propio**, conserva `id_solicitud` (el REQ exacto que atendió) y
  conserva `id_operacion` (estable entre reintentos). Así se cumple el §11.
- `a`, `b` y `resultado` son números finitos. El servidor rechaza operandos que no sean números (o
  que sean `bool`) con `error`. Si el resultado no es finito (por ejemplo, un overflow) también
  responde con `error`. Nunca se manda NaN ni Infinity.

**Intereses** (filtrado por código, al estilo ACP)

| Célula | Procesa | Ignora |
|---|---|---|
| Servidor X | `X_REQ`; `X_ACK` (para conocer a las que acusaron); `X_RES` (para saber que ya se respondió) | Todo lo demás. Los `SRV_LAT` se ignoran **sin registrarlos** (solo cuentan), para no inundar la bitácora. |
| GUI | `*_ACK` y `*_RES` **solo si `id_operacion` es suya**; `SRV_LAT` | `*_REQ` siempre, así que **no ve las solicitudes de otras GUIs**. Los ACK y RES ajenos van a la bitácora técnica como `IGNORA`, nunca a la vista. |

### 4.4 Broadcast y prevención de ciclos (§9, §11) — `nodo/nucleo.py`
```
al recibir una línea de datos por el enlace L (que ya pasó el HOLA):
  validar estructura: id hex de 64 · codigo str no vacío · origen str · ttl int · ruta list[str] · cuerpo dict
      si falla → DROP(motivo); return
  si not vistos.marcar_si_nuevo(id) → DUP (contador y bitácora); return     # §11: no se retransmite
  ttl = min(ttl, TTL_MAX)
  si ttl <= 0 → TTL_AGOTADO; return                                        # no se procesa
  ttl -= 1; ruta.append(mi_hash)
  datos = serializar UNA vez
  entregar a TODAS las células registradas, excepto L
  si ttl > 0: encolar a cada vecino NODO, excepto L y los que ya están en ruta
  si no: TTL_AGOTADO("no se reenvía a nodos")
  bitácora FWD: código, id8, origen, de, ruta (nombres), destinos (n nodos / n células)
```
- **Semántica del TTL**: cuántos nodos más pueden procesar el mensaje. Las células publican con
  `TTL_INICIAL` = 8. El TTL debe ser ≥ al diámetro de la red; en la malla completa el diámetro es 1.
  Con `sonda --ttl 1` solo lo procesa el primer nodo, que lo entrega a sus células y registra
  `TTL_AGOTADO`.

**Las 4 defensas**, documentadas en el reporte:
1. **Id único + registro temporal.** `RegistroVistos` es un `OrderedDict id → expira`, con vigencia
   de 60 s, tope de 100 000, purga perezosa desde el frente y lock. `marcar_si_nuevo` es atómico,
   así que dos hilos con copias simultáneas no pueden reenviar ambos.
2. **TTL**: acota el recorrido aunque el registro ya haya olvidado el id. Ese es el límite honesto
   del registro temporal: un duplicado que llegara después de 60 s volvería a circular, y el TTL lo
   frena.
3. **Horizonte dividido + ruta**: nunca se devuelve al enlace de entrada ni a nodos que ya lo
   procesaron.
4. **Deduplicación en la célula** (su propio `RegistroVistos`): cubre las copias que pueden llegar
   después de un failover.

La inundación es genérica y funciona con cualquier topología. En la malla de 4, cada nodo recibe
una copia útil y dos duplicadas: son la evidencia en vivo de los `DUP`.

---

## 5. Flujo de una operación y respuesta única

### 5.1 GUI — `interfaz/nucleo.py` (lock sobre `operaciones` y `vivas`)
1. El usuario captura `a op b` y pulsa `=`. Se valida que haya conexión y que el servicio siga
   **habilitado en ese momento**; si se deshabilitó después de elegir el operador, se avisa
   `SUM no disponible` y no se envía.
2. Se crea `id_operacion` y se **registra la operación ANTES de publicar**; si no, un acuse muy
   rápido podría llegar antes de que exista. Luego se publica `X_REQ` (intento 1). Hay **una
   operación en vuelo a la vez** (`=` deshabilitado mientras tanto).
3. Cada `X_ACK` con un `id_operacion` mío suma su `origen` a `acusadores[intento]`. Es un
   **conjunto por intento**: no se acumula entre intentos, porque una célula que acusó el intento 1
   y luego murió ya no tiene la operación. Mini log:
   `ACUSE 3/2 de SUM-N3 (ab12cd34) · intento 2`. Los ACK de intentos anteriores se registran,
   pero no cuentan.
4. **Quórum** = `len(acusadores[intento_vigente]) >= acuses_min[X]`. El `X_RES` se **acepta solo con quórum**: si
   llega antes, se **retiene**. Al alcanzar el quórum (por la llegada de un ACK o en el chequeo del
   reloj) se acepta el retenido. Justificación para el reporte: el mínimo de acuses garantiza que
   al menos K células tienen la operación en su cola, que son las que pueden relevar a la titular.
5. Plazos, revisados por un reloj de 100 ms:
   - **Sin quórum** a `VENTANA_ACUSES` (1.5 s) desde el envío del intento actual → **reintento**
     (mismo `id_operacion`, `intento+1`, id de mensaje nuevo). Si se agota `MAX_INTENTOS` (3) →
     `FALLIDA: acuses insuficientes (k/min)`.
   - **Con quórum pero sin resultado**, el plazo es dinámico:
     `t_quorum + VENTANA_ELECCION + RELEVO·max(1, n_acusadores) + MARGEN_RESULTADO (2 s)`. Al
     vencer → reintento; si se agotan los intentos → `FALLIDA: sin respuesta`.
6. Primer `X_RES` aceptable → `RESUELTA` y se muestra en el display. Mini log:
   `RESULTADO 12 · titular SUM-N2 · solicitud a1b2… ↔ respuesta 9f3e… · 512 ms`.
7. Respuestas que llegan después:
   - para una operación `RESUELTA` → `DUPLICADA descartada` (última línea de defensa; en
     condiciones normales no ocurre);
   - para una operación `FALLIDA` → `TARDÍA descartada`.

   Se guardan las últimas 200 operaciones propias para poder clasificar esas respuestas.
8. El display queda con el resultado para encadenar operaciones (como en el primer parcial). Si
   hay error, muestra `ERROR` y el texto.

### 5.2 Servidor — `servidor/nucleo.py`
**Estado.** `rondas[(id_operacion, intento)]` guarda `a`, `b`, `id_solicitud`, `t_rx`,
`acusadores: set`, `tiene_req: bool`, `estado` (`en_cola`, `titular`, `respaldo`, `resuelta` o
`superada`) y `creada`. Hay además una `queue.Queue` FIFO y un lock. Las rondas de más de 120 s se
purgan.

1. **RX `X_REQ`**:
   - si la ronda ya tiene REQ, se ignora (se registra);
   - si no: se publica **`X_ACK` de inmediato**, en el hilo lector y antes de encolar (el
     `--retardo-ms` **nunca** retrasa el acuse);
   - se agrega a sí misma a `acusadores` y marca `tiene_req`;
   - toda ronda **anterior** de la misma operación pasa a `superada` (la GUI ya pasó a otro intento);
   - se **encola** y se registra `ACUSE` y `COLA (n en espera)`.
2. **RX `X_ACK`** de otra célula: suma `origen` a `acusadores` de esa ronda. **Si la ronda no
   existe, la crea como "esqueleto"** (sin REQ): un acuse puede llegar *antes* que el REQ porque
   viajan por caminos distintos de la malla.
3. **RX `X_RES`** de la ronda k: marca como `resuelta` las rondas con intento **≤ k** de esa
   operación. **No** toca rondas futuras: un reintento posterior significa que la GUI no recibió
   esa respuesta y debe atenderse.
4. **Trabajador** (un hilo): toma una ronda, espera hasta `t_rx + VENTANA_ELECCION` (0.5 s) para
   juntar acuses, y ordena `acusadores` por `huella.prioridad(...)` (rendezvous hashing / HRW).
   Sea `r` su posición:
   - estado `resuelta` o `superada` → `RETIRADA`;
   - `r == 0` → **TITULAR**: aplica `--retardo-ms`, calcula, **vuelve a revisar el estado** (si ya
     se resolvió o se superó → `SUPRIMIDA`, no envía) y publica `X_RES` con `rol="titular"`;
   - `r > 0` → **RESPALDO**: agenda en un hilo programador (heap) el chequeo
     `t_rx + VENTANA_ELECCION + r·RELEVO`. Al vencer, si la ronda sigue sin resolver ni superar, la
     reencola como **RELEVO** (se ejecuta igual que la titular, con doble revisión y
     `rol="relevo r"`); si no, `RESPALDO LIBERADO`.
5. **Latido**: un `SRV_LAT` al conectarse o reconectarse (presentación inmediata) y luego cada
   `LATIDO` (2 s).

**Propiedades** (van al reporte):
- **Respuesta única** en condiciones normales: todas calculan el mismo ranking sobre el mismo
  conjunto de acusadores, sin mensajes extra ni coordinador.
- **Sin punto único de falla**: si la titular muere después de acusar, la rank 1 responde a ~1.5 s,
  y así sucesivamente.
- **Balanceo**: HRW reparte las titularidades de manera uniforme.
- **Ventana de carrera, explicada con honestidad**: si un acuse llega después de la ventana de
  elección (por ejemplo, una célula muy atrasada), dos células podrían creerse titulares. Hay tres
  capas que lo absorben: la doble revisión antes de enviar (la tardía suele ver la respuesta y
  suprime), la regla de superada y la deduplicación en la GUI.
- **Un reintento es una ronda nueva**: el `intento` entra al hash, así que puede tocar otra
  titular, y las rondas viejas quedan superadas.
- **Errores de dominio**: la división entre cero y los operandos inválidos se responden con
  `error`. Son respuestas válidas, no fallas.

### 5.3 Disponibilidad por latidos (GUI)
- `vivas[servicio][hash] = (último_visto, nombre, nodo_nombre)`. Se actualiza con cada `SRV_LAT`
  **y con cada `X_ACK`** (un acuse también prueba vida). Una célula caduca a los
  `LATIDO_CADUCIDAD` (6 s), es decir, después de 3 latidos perdidos. Eso cubre de sobra un
  failover (~2–3 s, y el servidor manda latido apenas reconecta).
- **Estado inicial**: todo deshabilitado con `esperando latidos…`; en ≤ 2 s se habilita.
- Si `len(vivas[X]) < acuses_min[X]`, se deshabilita el operador y se registra
  `SUM deshabilitada: 1 viva < 2 mínimas`. Al recuperarse, se registra
  `SUM habilitada: 2/2 (nueva: SUM-N2b · ab12cd34)`. Ahí se ve **cómo se integra una célula
  nueva**: se presenta, su primer latido llega al instante y el operador se rehabilita.
- `acuses_min` por operación: el valor por defecto se pasa con `--acuses-min` (2) y se **ajusta en
  vivo** con un Spinbox por operación (rango de 1 a 16). El quórum se evalúa con el valor vigente.

---

## 6. Interfaces gráficas y herramientas

**Ventana del nodo** (`nodo/gui.py`, Tkinter/ttk, ~720×450, `--geometria`):
- **Encabezado**: `Nodo 1 · ab12cd34 · escucha 127.0.0.1:5001`.
- **Contadores**: recibidos, reenviados, **duplicados descartados**, TTL agotado e ids en el
  registro temporal.
- **Tabla "Vecinos: 3"**: nombre, hash8, endpoint, entrante/saliente, desde.
- **Tabla "Células: 5 (1 GUI + 4 servidores)"**: tipo, servicio, nombre, hash8, desde.
- **Tráfico**: hora, evento (FWD, DUP, TTL, DROP, CONEXION, DESCONEXION, LENTO), código, id8,
  origen, de, ruta (`N1→N3`) y destinos. Colores por evento. Casillas "ocultar latidos" (marcada) y
  "pausar". Tope de 500 filas; los eventos se aplican en lote en cada `after`.
- Los nombres de la ruta salen de `vecinos`; si un hash no se conoce, se muestra el hash8.
- Al cerrar la ventana se cierran los sockets, y los pares lo detectan.

**Ventana de la GUI** (`interfaz/gui.py`). Se adaptan el teclado, el display y los atajos de
`proyecto_computo_distribuido/cliente/gui.py`, más `±` y `⌫`.
- Estado: `● conectada a Nodo 1 (127.0.0.1:5001)`, `● failover → Nodo 3` o `● sin Campo de Datos`.
- Panel **Disponibilidad**: por operación, símbolo, `vivas: 4`, Spinbox `mín. acuses` y ✓/✗.
- **Mis operaciones**: `7 ÷ 2 = 3.5 · acuses 4/2 · titular DIV-N3 · 512 ms · op a1b2c3d4`.
- **Mini log de protocolo**: SOLICITUD, ACUSE, QUÓRUM, RESULTADO, REINTENTO, FALLIDA,
  DESHABILITADA/HABILITADA, FAILOVER, DUPLICADA y TARDÍA.
- Números: los flotantes enteros se muestran como enteros si |x| < 1e15; el resto con `.12g`
  (así `0.1+0.2` muestra `0.3`). Se adapta `formato.numero` del primer parcial.

**Servidor**: sin ventana. Su bitácora va a consola y archivo:
`RX, ACUSE, COLA, TITULAR, RESPALDO, RELEVO, RETIRADA, SUPRIMIDA, LIBERADO, RES, IGNORA, FAILOVER`.
Los colores ANSI solo se usan si `stdout.isatty()`, para que en el panel no aparezcan códigos
basura.

**Panel de despliegue** (`panel/`). Lleva el rótulo *"Herramienta de despliegue: no forma parte del
sistema ADS; solo lanza procesos del sistema operativo. Todo se puede lanzar a mano."*
- **Matriz**: filas Nodo 1..N y columnas `Nodo | GUI | + | − | × | ÷`. Cada casilla muestra ● con
  el conteo de instancias vivas, ▶ para levantar una más y ■ para tumbar la más reciente (simula
  una caída con `terminate()`). **"+ Nodo"** agrega una fila (puerto `5000+k`).
- **"Levantar configuración mínima"** levanta **solo lo que falte** de 4 nodos × 5 células:
  primero los nodos y ~1 s después las células. También están **"Detener todo"** y un Spinbox
  "retardo ms" para levantar células lentas.
- **Semilla del nodo k**: un nodo vivo elegido **al azar**, o ninguno si es el primero. Demuestra
  que basta conocer a cualquiera y que ningún nodo es especial. Si la semilla aún no escucha, el
  marcador reintenta.
- **Lista de procesos**: nombre, tipo, nodo, PID, estado (vivo o terminado con su código) y
  **comando exacto**. Al seleccionar uno se ve su bitácora en vivo (últimas 2 000 líneas); también
  se puede tumbar el seleccionado.
- **Lanzamiento**: `Popen([sys.executable, "-u", "-m", mod, ...], cwd=raíz, stdout=PIPE,
  stderr=STDOUT, creationflags=CREATE_NO_WINDOW, env={…, "PYTHONIOENCODING": "utf-8"})`. Un hilo
  lector por proceso, para que el pipe nunca se llene y bloquee al hijo, y `poll()` cada 500 ms.
- Acomoda las ventanas con `--geometria`: nodos en 2×2 y GUIs en cascada, calculado con
  `winfo_screen*`. Es una sugerencia; el usuario las mueve.
- Al cerrar pregunta si se detienen los procesos. Si no, los hijos siguen vivos: su bitácora
  tolera el pipe roto y sigue escribiendo en archivo.

**Sonda** (`sonda/`, CLI). Se presenta como `SONDA`, inyecta `SONDA_PRUEBA`, imprime el id usado y
termina.
- `--ttl 1` → solo lo procesa el primer nodo, que registra `TTL_AGOTADO`. `--ttl 0` → el primer
  nodo lo descarta completo.
- `--repetir N` → manda la **misma** copia N veces al mismo nodo: la primera se reenvía y las demás
  son `DUP` **en ese nodo**. Ojo: no llegan a los demás, porque el primer nodo ya no las reenvía; esa
  es justamente la evidencia.
- `--id <hash>` → reinyecta un id ya visto **por otro nodo** (por ejemplo, el id que imprimió una
  sonda en el Nodo 1, reinyectado ahora en el Nodo 3). El Nodo 3 lo marca `DUP` y no lo retransmite,
  lo que demuestra el §11 en **cualquier** nodo mientras el id siga vigente (60 s).

**Bitácora** (`comun/bitacora.py`):
- Formato: `HH:MM:SS.mmm [EVENTO] texto`.
- Se escribe en consola con flush, envuelta en `try` (si el pipe está roto o cerrado, se ignora),
  y en `logs/<nombre>-<hash8>.log`, también envuelto en `try`.
- Ofrece un callback opcional para la GUI. Nunca lanza excepciones.

---

## 7. Constantes — `comun/config.py` (las pruebas las acortan)

| Constante | Valor | Constante | Valor |
|---|---|---|---|
| `TTL_INICIAL` | 8 | `TTL_MAX` | 16 |
| `VISTOS_VIGENCIA` | 60 s | `VISTOS_MAX` | 100 000 |
| `LATIDO` | 2 s | `LATIDO_CADUCIDAD` | 6 s |
| `VENTANA_ACUSES` | 1.5 s | `VENTANA_ELECCION` | 0.5 s |
| `RELEVO` | 1.5 s | `MARGEN_RESULTADO` | 2 s |
| `MAX_INTENTOS` | 3 | `ACUSES_MIN_DEFECTO` | 2 |
| `HOLA_TIMEOUT` | 5 s | `BIENVENIDA_TIMEOUT` | 3 s |
| `BACKOFF_MIN/MAX` | 1 / 8 s | `SUPERVISOR` | 2 s |
| `REINTENTOS_MISMO_NODO` | 2 | `MAX_LINEA` | 64 KiB |
| `COLA_ENLACE_MAX` | 5 000 | `RONDAS_VIGENCIA` | 120 s |

---

## 8. Casos borde y cómo se manejan

| Caso | Manejo |
|---|---|
| Línea que no es JSON o mensaje mal formado | `DROP` con motivo; el enlace **sigue** vivo. |
| Datos antes del `HOLA`, o sin `HOLA` en 5 s | Se descartan; al vencer el plazo se cierra. |
| Versión distinta o entidad desconocida | `RECHAZO` y se cierra. |
| Dos nodos se marcan a la vez, o hay endpoints alias | Regla de enlace duplicado (§4.2 punto 4). |
| Un nodo recibe su propio endpoint por gossip | `RECHAZO(autoconexion)` y queda marcado como propio. |
| Puerto ocupado | El nodo sale con un mensaje claro y código 1. |
| Par lento o colgado | Cola de escritura por enlace; si se desborda, se cierra con `LENTO`. Nadie más se bloquea. |
| Copias simultáneas del mismo id por dos enlaces | `marcar_si_nuevo` atómico: solo una se reenvía. |
| ACK que llega antes que el REQ | Se crea una ronda esqueleto que se completa con el REQ. |
| La titular muere después de acusar | La rank 1 hace el relevo; si muere también, la rank 2, etc. |
| Titular lenta (`--retardo-ms`) | El relevo responde, y la titular ve la respuesta y suprime la suya. |
| Respuesta perdida (por ejemplo, cae un nodo en tránsito) | La GUI agota el plazo y reintenta; la ronda nueva sí se atiende (regla ≤ k). |
| Reintento mientras la ronda vieja sigue en cola | La ronda vieja pasa a superada y no responde. |
| Llega un RES y luego otro de la misma operación | La GUI registra `DUPLICADA descartada`. |
| Llega un RES después de una `FALLIDA` | `TARDÍA descartada`. |
| RES antes del quórum | Se retiene hasta el quórum o hasta el fallo. |
| Una célula acusó un intento anterior y murió | No cuenta: el quórum es solo del intento vigente. |
| Menos células vivas que el mínimo | Operador deshabilitado y mini log; se rehabilita con latidos. |
| El servicio se deshabilita con el operador ya elegido | Al pulsar `=`, se avisa `no disponible`. |
| Cae el nodo de una célula | Failover a otro nodo; el hash de la célula se conserva. |
| Caen todos los nodos | La célula cicla con backoff; la GUI muestra `sin Campo de Datos`. |
| Una célula se reconecta antes de que el nodo detecte su enlace viejo | Gana el enlace nuevo y el viejo se cierra. |
| Publicar sin conexión | Se pierde y se registra; los reintentos de la GUI lo cubren. |
| División entre cero, operandos inválidos o resultado no finito | `*_RES` con `error`; nunca NaN ni Infinity en el JSON. |
| El panel se cierra sin detener los procesos | Los hijos toleran el stdout roto y siguen con su bitácora en archivo. |
| Ruido de latidos | La GUI del nodo los oculta por defecto; las células no registran los `SRV_LAT` ignorados. |
| Diálogo del firewall de Windows | Se bindea a 127.0.0.1 por defecto. |
| Un duplicado llega después de 60 s | El registro ya lo olvidó, pero el TTL lo frena. Se documenta como límite. |
| Pantalla con escalado DPI | No se fuerza el modo DPI-aware; las coordenadas lógicas son consistentes con 1463×914. |

---

## 9. Cumplimiento del PDF (énfasis en §10, §11 y §14)

| § | Requisito | Cómo se cumple |
|---|---|---|
| 1 | Cualquier lenguaje | Python 3, sin dependencias (decisión consciente de no usar Java). |
| 4 | Las 4 operaciones vía Campo de Datos, broadcast y código | `servidor/calculo.py` + §4–§5. |
| 5 | Programas GUI, servidor configurable y nodo | `interfaz/`, `servidor --servicio`, `nodo/`. |
| 6 | 4 nodos en malla completa con 5 células cada uno; sin límites fijos | Gossip + supervisor; el panel levanta N nodos y N células; nada codificado. |
| 7 | Código en toda solicitud y respuesta; la respuesta trae el id original y el resultado | Tabla §4.3. |
| 8 | Estructura mínima del mensaje | Sobre §4.3. |
| 9 | Broadcast; evitar múltiples respuestas no deseadas | Inundación §4.4 + elección HRW §5.2. |
| **10.1** | Conectar los 4 nodos en malla | `HOLA`, `BIENVENIDA` y `PARES` + supervisor + regla de enlace duplicado. |
| **10.1** | Conectar GUIs y servidores a cada nodo | `HOLA` con `entidad`. |
| **10.1** | Identificar el tipo de entidad y controlar las conexiones activas | Tablas `vecinos` y `celulas`, visibles en la ventana del nodo. |
| **10.1** | Independiente del número de instancias | Sin listas fijas; basta una semilla cualquiera; se prueba con un 5º nodo y con células extra. |
| **10.2** | Broadcast entre nodos y células | §4.4. |
| **10.2** | Transporta códigos de solicitud y respuesta | Campo `codigo`. |
| **10.2** | Impide la circulación indefinida | TTL + registro de vistos + ruta + horizonte dividido. |
| **10.2** | Detecta mensajes ya recibidos | `RegistroVistos` en nodo y célula. |
| **10.2** | Asocia la respuesta con la solicitud | `id_operacion` + `id_solicitud` en ACK y RES. |
| **11** | Id único por mensaje | `huella.de_mensaje`. |
| **11** | Registro **temporal** de ids procesados | Vigencia de 60 s, visible en el contador del nodo. |
| **11** | No retransmitir un id repetido | `DUP`; demo con `sonda --repetir` y `sonda --id`. |
| **11** | La respuesta tiene id propio y referencia a la solicitud | `RES.id` ≠ `cuerpo.id_solicitud`. |
| **11** | Estrategia documentada contra duplicados con varios servidores | Acuses → HRW → respaldos escalonados → doble revisión → superada → deduplicación en la GUI. |
| 12 | Flujo de 10 pasos | Se reproduce en el reporte con bitácoras reales. |
| 13 | Esquema conceptual | Diagrama en el reporte. |
| **14** | Evidencias | Ver §10. |
| 15 | Descentralización y sin punto único de falla; formato documentado; recorrido observable | Gossip, inundación sin tablas de ruteo, elección sin coordinador, failover, `ruta`, bitácoras y ventanas. |

---

## 10. Evidencias del §14 y dónde se ven

| Evidencia | Dónde |
|---|---|
| Nodos 1–4 en malla completa | "Vecinos: 3" con nombres en cada ventana; matriz del panel. |
| GUI + servidores +, −, ×, ÷ en cada nodo | "Células: 5 (1 GUI + 4 servidores)" en cada nodo; matriz 4×5 del panel. |
| Solicitudes con código | Mini log de la GUI `SUM_REQ`; `FWD SUM_REQ` con ruta en los 4 nodos; `RX` y `ACUSE` en los 4 SUM. |
| Respuestas con código de respuesta | `FWD SUM_RES` en los nodos; RESULTADO en la GUI. |
| Asociación solicitud ↔ respuesta | La GUI muestra `op`, `solicitud` y `respuesta`; la bitácora de la titular también. |
| Prevención de ciclos y duplicados | Filas y contador de `DUP`; `sonda --ttl 1`; `sonda --repetir 3`; `sonda --id`. |
| Una sola respuesta (§9) | 1 TITULAR + 3 LIBERADO; con una célula lenta: RELEVO + SUPRIMIDA. |
| Las 4 operaciones correctas | Una desde cada GUI, más la división entre cero. |
| Sin punto único de falla (§15) | Tumbar el Nodo 1 → failover de sus 5 células; tumbar 3 DIV → DIV deshabilitada; levantar una → habilitada; "+ Nodo" → malla de 5. |

---

## 11. Fases de trabajo (orden estricto, como pidió el usuario)

**Fase 0 — Preparación**
- Crear `calculadora_ads/` y hacer `git init`.
- Copiar este plan a `docs/PLAN.md`.
- Crear `ROADMAP.md` (§17) y un `CLAUDE.md` mínimo con las decisiones de §0.1, cómo correr y
  dónde está cada cosa.
- Guardar en la memoria del asistente las preferencias del usuario: el orden de fases, Python, que
  el PDF manda sobre la clase (mencionando las diferencias con respeto) y el estilo del reporte.

**Fase A — Código.** Después de cada bloque se corre una prueba de humo manual (importar y
arrancar headless); la suite formal es de la fase B.
1. `pyproject.toml`, `.gitignore`, paquetes y `comun/*`.
2. `nodo/nucleo.py` + `nodo/__main__.py --sin-ventana` + `sonda/`.
   Humo: 4 nodos headless + sondas.
3. `celula/base.py` + `servidor/` + `interfaz/nucleo.py`.
   Humo: un script temporal en la carpeta scratch que manda una operación.
4. `nodo/gui.py` + `interfaz/gui.py`.
5. `panel/`.

**Fase B — Pruebas.** Suite completa (§12) y verificación en vivo (§14).

**Fase C — Fixes.** Corregir todo lo encontrado y repetir la fase B hasta que quede limpia. El
resultado se reporta tal cual, sin maquillar.

**Fase D — Reporte.**
- README, ENTREGA y CLAUDE.md completos.
- `REPORTE_TECNICO.md` escrito sobre el sistema ya probado, con extractos de bitácoras reales.
- Conversión a `.docx` con el skill de docx (pandoc no está instalado).

**Fase E — Guion.** `GUION_VIDEO.md`, amarrado a las secciones del reporte y a la tabla §10.

---

## 12. Pruebas (`py -m unittest discover -s tests -t .`)

**Unitarias**
- `test_protocolo`: mensaje partido, mensajes pegados, cierre, **línea inválida que no rompe el
  lector**, tope `MAX_LINEA` y `allow_nan`.
- `test_enlace`: la cola de escritura no bloquea; el desborde cierra el enlace.
- `test_huella`: 64 hex, 50 000 hashes únicos, ranking determinista e independiente del orden del
  conjunto, reparto ~uniforme sobre 4 células en 4 000 operaciones.
- `test_mensajes`: construcción, validación de cada campo y catálogo completo.
- `test_vistos`: nuevo, repetido, caducidad con reloj falso, tope, atomicidad con hilos.
- `test_calculo`: 4 operaciones, división entre cero, no finito, `bool` y `str` como operandos.
- `test_formato`.

**Integración** (en proceso, puertos efímeros, tiempos acortados)
- `test_malla`:
  - 4 nodos con semillas en cadena forman la malla completa (3 vecinos cada uno, **sin enlaces
    duplicados**);
  - dos nodos que se marcan a la vez convergen a un enlace;
  - autoconexión rechazada;
  - un 5º nodo con una sola semilla se integra;
  - tumbar un nodo lo saca de las tablas.
- `test_broadcast`:
  - un mensaje de la sonda llega **exactamente una vez** a cada célula;
  - hay DUP > 0 en los nodos;
  - `ttl=1` solo llega a las células del primer nodo;
  - `ttl=0` no llega a nadie;
  - el id repetido es DUP en el nodo donde se reinyecta;
  - la `ruta` es correcta;
  - una línea basura no tumba el enlace.
- `test_flujo`, sistema completo (4 nodos, 16 servidores y 4 interfaces):
  - 4 operaciones correctas;
  - ≥ 2 acuses y **exactamente un `*_RES`** por operación (contado con una célula espía);
  - las otras interfaces no registran la operación;
  - división entre cero;
  - titular lenta → relevo + suprimida;
  - titular tumbada después de acusar → relevo;
  - nodo tumbado → failover y el servicio sigue;
  - 3 SUM tumbadas → SUM deshabilitada; levantar una → habilitada;
  - reintento con el mismo `id_operacion` atendido (la regla ≤ k);
  - quórum por intento: un acuse viejo de una célula muerta no cuenta;
  - ronda vieja superada sin respuesta extra;
  - ACK antes del REQ (inyectado a mano) → ranking correcto.
- Posible inestabilidad: las aserciones de "exactamente uno" usan `RELEVO` ≥ 1 s incluso en
  pruebas, para que la carga de la máquina no provoque relevos falsos.

---

## 13. Reutilización (se declara en el reporte, sección de originalidad)

| De | A | Cambio |
|---|---|---|
| `proyecto_computo_distribuido/comun/protocolo.py` | `comun/protocolo.py` | Lector tolerante a líneas inválidas, `MAX_LINEA`, `allow_nan=False`, Enlace con cola. |
| `proyecto_computo_distribuido/servidor/calculo.py` | `servidor/calculo.py` | Un servicio por llamada; control de no finitos y de tipos. |
| `proyecto_computo_distribuido/comun/formato.py` | `comun/formato.py` | `.12g` y tope para mostrar como entero. |
| `proyecto_computo_distribuido/cliente/gui.py` | `interfaz/gui.py` | Teclado, display, atajos y patrón cola + `after(100)`. |
| `proyecto_computo_distribuido/tests/test_protocolo.py` | `tests/test_protocolo.py` | Base de `FuenteFalsa`. |

Además se toman **ideas, no código**, de `Practica3/`: lock de envío por socket, gossip de pares,
validación estructural y filtrado por intereses (ACP/ASM). Todo el código restante es original.

---

## 14. Verificación de punta a punta (Fase B)

1. `py -m unittest discover -s tests -t .`: todo en verde. Opcional: `uvx ruff check .`.
2. `py -m panel` → "Levantar configuración mínima". En `logs/` debe verse:
   - cada nodo con 3 vecinos y 5 células;
   - por operación: 4 `ACUSE`, 1 `TITULAR`, 3 `LIBERADO` y un solo `RES`;
   - las otras GUIs con `IGNORA` sobre el REQ ajeno.
3. Capturas de pantalla con PowerShell y `System.Drawing` para revisar las ventanas a 1463×914:
   legibilidad, que nada se corte y que las tablas se llenen.
4. Escenarios en vivo:
   - tumbar el Nodo 1 → failover;
   - tumbar 3 DIV → deshabilitada; levantar una → habilitada;
   - `--retardo-ms 4000` → relevo + suprimida;
   - `sonda --ttl 1`, `--repetir 3` e `--id`;
   - "+ Nodo" → malla de 5;
   - cerrar el panel sin detener → los hijos siguen.

---

## 15. Documentación (fases D y E)

- **README.md**: qué es, arranque (`py -m panel`), comandos manuales, estructura y decisiones.
- **REPORTE_TECNICO.md**, con el estilo del primer parcial.
  - **Portada** con marcadores: `<NOMBRE>`, `<MATRÍCULA>`, `<GRUPO>`, `<LIGA REPO>`, `<LIGA VIDEO>`.
  - **Parte I**: introducción, objetivos, alcance y matriz de trazabilidad §1–§15 (archivo y
    función, sección y minuto del video).
  - **Parte II**:
    1. Arquitectura ADS (Campo de Datos, células, código de contenido, autonomía; ACP/ASM).
    2. Topología y descubrimiento.
    3. Protocolo de conexión y protocolo de comunicación, con tablas.
    4. Catálogo de códigos y formato de mensajes.
    5. Broadcast.
    6. Prevención de ciclos (las 4 defensas).
    7. Acuses y mínimo.
    8. Respuesta única, con diagramas de tiempo: normal, relevo y célula lenta.
    9. Latidos.
    10. Hashes.
    11. Failover.
    12. Concurrencia (hilos, locks, colas).
    13. Tolerancia a fallas (tabla de §8).
    14. Pruebas.
    15. Panel y sonda.
    16. Decisiones de implementación.
    17. **"Diferencias respecto a lo visto en clase"**, breve y respetuoso:
        - latidos en vez de solo acuses, por reacción inmediata a altas y bajas;
        - respuesta única por elección en vez de "todas responden", porque el §9 del PDF pide
          evitarlas.
  - **Parte III**: conclusiones, limitaciones y **trabajo futuro** (algoritmo de foliado, células
    que levantan células, detección de enlaces medio abiertos, seguridad y autenticación).
  - Glosario y referencias APA: Mori 1993 (ADS); Tanenbaum y Van Steen; Coulouris et al.; Thaler y
    Ravishankar 1998 (HRW); Demers et al. 1987 (algoritmos epidémicos).
- **GUION_VIDEO.md**: escenas amarradas a la tabla §10, con qué decir en cada una (incluidas las
  dos notas frente a la clase), checklist previo, prueba de micrófono y tabla de minutos para
  regresar a la matriz del reporte.
- **ENTREGA.md**: estado de los 3 entregables y lo que hace el usuario a mano (portada, grabar,
  push y ligas).
- **Commits**: solo cuando el usuario lo pida.

---

## 16. Registro de revisión (bugs del borrador anterior, cada uno validado dos veces)

| # | Bug del borrador | Escenario que lo confirma | Corrección |
|---|---|---|---|
| 1 | Un RES marcaba "todas las rondas" como resueltas | Se pierde el RES de la ronda 1 (cae el nodo de la GUI) → la GUI reintenta → todas se retiran → nadie responde → FALLIDA | Un RES resuelve solo las rondas ≤ k |
| 2 | "Todos los nodos marcan DUP" con `--repetir-id` | La 2ª copia muere en el primer nodo y nunca llega a los demás | `--repetir` (DUP en ese nodo) + `--id` para reinyectar en otro nodo |
| 3 | El ACK podía llegar antes que el REQ y perderse | Caminos distintos en la malla (N1→N2 contra N1→N3→S3→N3→N2) y planificación de hilos | Rondas esqueleto creadas por el ACK |
| 4 | `leer_mensajes` del 1er parcial cierra el enlace con una línea inválida | La excepción dentro del generador lo termina | Lector tolerante por línea |
| 5 | `sendall` bloqueante dentro del hilo lector | Un par que no lee llena el buffer y congela la inundación de todos | Cola y hilo escritor por enlace, con tope |
| 6 | El panel cerrado tumba a los hijos | Escribir en un pipe cerrado lanza `OSError` | Bitácora tolerante + pregunta al cerrar |
| 7 | Bind a 0.0.0.0 | Diálogo del firewall de Windows a media demo | 127.0.0.1 por defecto, `--host` para LAN |
| 8 | La regla de enlace duplicado no cubría aliases | Dos enlaces iniciados por el mismo lado | Regla general + alias |
| 9 | Ronda vieja que responde después de un reintento | Respuesta extra innecesaria | Estado `superada` |
| 10 | `json.dumps` permite Infinity | JSON no estándar ante overflow | `allow_nan=False` + chequeo de finitos |
| 11 | Plazo de resultado fijo (8 s) | Con muchas células, el relevo de rank alto llega tarde | Plazo dinámico por número de acusadores |
| 12 | Imports `from config import X` | Las pruebas no podrían acortar tiempos | Regla `config.X` |
| 13 | Registrar la operación después de publicar | El ACK podría llegar antes del registro | Registrar antes |
| 14 | Pruebas unitarias dentro de la fase de código | Contradecía el orden pedido | Fase A solo humo; suite en B |
| 15 | Faltaban: estado inicial de la GUI, operador deshabilitado tras elegirlo, RES tardío, ruido de latidos e IGNORA, ANSI en pipe | — | Definidos en §5, §6 y §8 |
| 16 | La GUI acumulaba acusadores entre intentos | S1 acusa el intento 1 y muere; en el intento 2 solo acusa S2; el acumulado {S1, S2} da quórum falso 2/2 | Quórum por intento vigente |

---

## 17. Roadmap por sesiones (se materializa en `ROADMAP.md` en la Fase 0)

`ROADMAP.md` tiene una casilla por entregable de cada sesión, una sección **"Estado actual /
siguiente paso"** y un **registro de sesiones** (fecha, qué se hizo, qué quedó pendiente y
problemas abiertos).

**Protocolo de cada sesión:**
- **Al iniciar**: leer `ROADMAP.md`, `CLAUDE.md` y `docs/PLAN.md` y retomar en "siguiente paso".
- **Al cerrar**: marcar las casillas, actualizar "Estado actual" y anotar la sesión. Ninguna sesión
  cierra con código a medias sin anotarlo.

| Sesión | Fases | Entregables | Criterio de salida |
|---|---|---|---|
| **S1** | 0 + A1–A2 | Carpeta, git, `docs/PLAN.md`, `ROADMAP.md`, `CLAUDE.md`, `comun/*`, `nodo/nucleo.py` headless, `sonda` | 4 nodos headless forman la malla completa; las sondas muestran FWD, DUP y TTL en las bitácoras |
| **S2** | A3 | `celula/base.py`, `servidor/`, `interfaz/nucleo.py` | Un script de humo resuelve las 4 operaciones con un solo RES, y hay failover al tumbar un nodo |
| **S3** | A4–A5 | `nodo/gui.py`, `interfaz/gui.py`, `panel/` | Con el panel, la configuración mínima corre con ventanas y se puede operar a mano |
| **S4** | B + C | Suite completa, verificación en vivo, capturas, fixes | Todo en verde; los escenarios de §14 pasan; los hallazgos quedan corregidos y anotados |
| **S5** | D | README, ENTREGA, CLAUDE.md, REPORTE_TECNICO.md, `.docx` | Reporte completo; solo quedan los marcadores de portada y los minutos del video |
| **S6** | E | GUION_VIDEO.md, checklist final | El usuario puede grabar siguiendo el guion |

Si una sesión rinde de más, se adelanta la siguiente **sin saltarse el orden de fases**.
