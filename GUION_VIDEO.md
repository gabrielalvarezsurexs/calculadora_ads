# GUION DEL VIDEO — Calculadora ADS

Guion completo de la demostración. Duración objetivo: **~16 minutos** (15 escenas).

Cada escena trae: **qué se ve** en pantalla · **qué hacer** (clics y comandos exactos) · **qué
decir** (texto para leer o parafrasear). Las escenas siguen el orden de la corrida real del
reporte (sección 17.2): si se hacen en este orden, todo sale como se describe.

> El enunciado pide **video con audio**. Un video sin narración no cumple el entregable. Lo
> primero del checklist es probar el micrófono.

Las evidencias del §14 del enunciado y dónde se ven, escena por escena, están al final: esa tabla
es la que regresa a la columna "Video" de la matriz del reporte (§2).

---

## ANTES DE GRABAR — checklist

```powershell
cd c:\SCHOOL\COMPUTO_DISTRIBUIDO\calculadora_ads

# 1. Nada corriendo de antes: debe imprimir 0
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='py.exe'" |
  Where-Object CommandLine -match ' -m (nodo|servidor|interfaz|panel)( |$)' |
  Measure-Object | ForEach-Object Count

# 2. Guardar las bitácoras de la corrida del reporte y grabar con logs/ vacía
#    (los comandos de las escenas 6 y 7 cuentan TODO lo que hay en logs/)
if (Test-Path logs) { Rename-Item logs "logs_reporte_$(Get-Date -Format yyyyMMdd_HHmm)" }

# 3. Pruebas (~85 s). Deja esta salida en la terminal: se muestra en la escena 14
py -m unittest discover -s tests -t .
```

Checklist de grabación:

- [ ] **Prueba de audio: graba 10 segundos y escúchalos.**
- [ ] Grabador listo, **de pantalla completa**: OBS Studio ("Captura de pantalla" + micrófono) o
      Recortes de Windows en modo grabar con el micrófono activado. **No uses la Xbox Game Bar**:
      graba una sola ventana, y aquí hay nueve.
- [ ] No molestar activado (`Win+N` → No molestar).
- [ ] Cerrar correo, mensajería y cualquier ventana ajena al proyecto.
- [ ] Una terminal de PowerShell en la carpeta del proyecto, con letra grande (`Ctrl` + `+`).
- [ ] La lupa de Windows a la mano: `Win` + `+` acerca, `Win` + `Esc` la cierra. Sirve para
      señalar una línea del mini log o de la tabla de tráfico, que tienen letra chica.
- [ ] Este guion abierto en el celular o en otra pantalla, **no** en la que grabas.

### Dónde quedan las ventanas

El panel las acomoda solo. En tu pantalla quedan así:

```
 0                          728                              1463
 ┌──────────────────────────┬───────────────┬────────────────┐
 │ Nodo 1                   │ Nodo 2        │ GUI-1          │
 │                          │               │  GUI-2         │  las 4 GUIs en cascada,
 │                          │               │   GUI-3        │  encima de los Nodos 2 y 4
 ├──────────────────────────┼───────────────┤    GUI-4       │
 │ Nodo 3                   │ Nodo 4        │                │
 │                          │               │                │
 └──────────────────────────┴───────────────┴────────────────┘
   El panel arranca centrado arriba (780 × 640). El Nodo 5 (escena 12) sale encima del Nodo 1.
```

Todas se enciman: para mostrar una, **haz clic en su barra de título o en la barra de tareas**.
Cuando uses la terminal, ponla sobre el área del Nodo 1 (arriba a la izquierda) y maximízala
solo para los comandos con salida larga (escenas 6 y 7).

**No cierres con la X la ventana de un nodo**: eso detiene el nodo de verdad (para eso está la
escena 10, y ahí se hace desde el panel).

---

## ESCENA 1 — Presentación (0:30)

**Se ve:** el `README.md` del repositorio.

**Qué decir:**

> Buenas. Soy `<tu nombre>`, y este es el proyecto del segundo parcial de Cómputo Distribuido:
> la calculadora del primer parcial, adecuada a una arquitectura de sistemas autónomos
> descentralizados, ADS.
>
> En el primer parcial todo pasaba por un middleware, y ese middleware era un punto único de
> falla. Aquí ya no hay middleware ni servidor central: hay un Campo de Datos de nodos en malla, y
> las células se comunican solo por broadcast con Códigos de Contenido.
>
> Está hecho en Python, solo con la librería estándar: sockets TCP, hilos y Tkinter. No hay nada
> que instalar.

---

## ESCENA 2 — La arquitectura (0:45)

**Se ve:** el diagrama del `README.md` (sección "Qué hace"), o el de la sección 3.2 del reporte.

**Qué decir:**

> Esta es la arquitectura que pide el enunciado. Cuatro nodos forman el Campo de Datos, en malla
> completa: cada nodo está conectado con los otros tres. A cada nodo se conectan cinco células:
> una GUI y un servidor de cada operación. Veinte células en total.
>
> Los nodos son "bobos" a propósito: aceptan conexiones, retransmiten por broadcast y evitan los
> ciclos, pero nunca abren el contenido de un mensaje. Quien decide qué le interesa es cada
> célula, por el Código de Contenido: una célula de suma solo procesa `SUM_REQ`; todo lo demás lo
> ignora.
>
> Y todo tiene un identificador SHA-256 que genera cada quien: los nodos, las células, los
> mensajes y las operaciones. Nadie asigna identificadores, porque no hay a quién preguntarle.

---

## ESCENA 3 — Levantar el sistema (1:00)

**Qué hacer:**

```powershell
py -m panel
```

En el panel, clic en **"Levantar configuración mínima"**. Espera a que aparezcan las 8 ventanas
(primero los 4 nodos y, un segundo después, las 4 GUIs). Trae el panel al frente.

**Se ve:** el panel con la matriz de 4 × 6 en "● 1" y la lista de procesos con la columna
"comando".

**Qué decir:**

> Para la demostración uso este panel. Es importante aclararlo: el panel **no es parte del
> sistema**; lo dice en su rótulo. Solo lanza procesos del sistema operativo, y cada proceso se
> podría lanzar a mano con el comando que aparece aquí en la lista.
>
> Por ejemplo, el Nodo 2 es `py -m nodo --puerto 5002` con una semilla. Y un servidor es
> `py -m servidor --servicio SUM` conectado a su nodo: el mismo programa sirve para las cuatro
> operaciones, se configura con `--servicio`.
>
> Son 24 procesos independientes: 4 nodos y 20 células. Los servidores no tienen ventana; su
> bitácora se ve aquí abajo al seleccionarlos.

---

## ESCENA 4 — La malla y el control de conexiones (1:15)

**Qué hacer:** trae al frente la ventana del **Nodo 2**. Luego, en el panel, señala la columna
"comando" de los nodos 3 y 4 (la parte `--semillas`).

**Se ve:** "Nodo 2 · <hash> · escucha 127.0.0.1:5002", la tabla **"Vecinos: 3"** (con sentido
entrante/saliente) y la tabla **"Células: 5 (1 GUI + 4 servidores)"** (tipo, servicio, nombre y
hash de cada una).

**Qué decir:**

> Esta es la ventana del Nodo 2. Aquí se ve lo que pide el protocolo de conexión del §10.1.
>
> Arriba a la izquierda, sus vecinos: los otros tres nodos. La malla está completa. A la derecha,
> sus células: una GUI y cuatro servidores, cada uno identificado por tipo, servicio y hash. Esas
> dos tablas son el control de conexiones activas.
>
> ¿Cómo sabe el nodo quién es quién? Toda conexión empieza con un mensaje `HOLA` que dice qué
> entidad es: nodo, GUI o servidor. El nodo contesta `BIENVENIDA` con la lista de nodos que
> conoce, y cada vez que conoce uno nuevo se lo avisa a los demás con `PARES`. Es gossip.
>
> Fíjense en el panel: a cada nodo le di como semilla **un solo nodo, elegido al azar**. Nadie
> tiene la lista completa, y aun así la malla se completó sola en una fracción de segundo.
>
> Si dos nodos se marcan al mismo tiempo, quedan dos conexiones entre ellos. Una regla basada solo
> en los hashes hace que los dos se queden con la misma, sin hablarlo.

---

## ESCENA 5 — Una operación de punta a punta: 7 + 5 (2:15)

Esta es la escena más importante: aquí se ven los 10 pasos del §12. No la apresures.

**Qué hacer:**

1. Trae al frente la **GUI-1**. Con el mouse: `7`, `+`, `5`, `=`.
2. Señala, en este orden: el display (`12`), la línea de estado ("titular SUM-N… · acuses 4/2 ·
   ~510 ms"), la línea de "Mis operaciones" (anota el `op` de 8 caracteres: lo usas en la escena 7)
   y el **mini log de protocolo**.
3. Trae al frente el **Nodo 2** y marca **"pausar"** en la tabla de tráfico. Señala la fila
   `FWD SUM_REQ` (ruta `N1→N2`), las dos `DUP SUM_REQ` y la fila `FWD SUM_RES`. Desmarca
   "pausar".
4. En el panel, selecciona en la lista el servidor que respondió (el que dice la GUI, por ejemplo
   `SUM-N4`). Señala en su bitácora: `RX`, `ACUSE`, `COLA`, `TITULAR · rank 0 de 4` y `RES`.

**Se ve:** en el mini log, `SOLICITUD SUM_REQ 7 + 5 · op … · solicitud …`, cuatro `ACUSE`, el
`QUÓRUM 2/2` y `RESULTADO 7 + 5 = 12 · titular SUM-N… · solicitud … ↔ respuesta …`.

**Qué decir:**

> Hago una suma desde la GUI-1: siete más cinco.
>
> El resultado es 12, y abajo está el recorrido completo. La GUI generó una **solicitud con un
> identificador único** y el código `SUM_REQ`, y la mandó a su nodo, el Nodo 1.
>
> El Nodo 1 la difundió a los otros tres nodos y a sus células. Aquí en el Nodo 2 se ve que la
> recibió del Nodo 1, con la ruta N1 → N2: ese campo `ruta` es el recorrido observable del
> mensaje. Y luego le llegaron dos copias más, del Nodo 3 y del Nodo 4: son `DUP`, ya las había
> procesado, así que no las retransmite.
>
> Las otras 19 células recibieron la solicitud, cada una exactamente una vez. Solo las cuatro de
> suma la procesaron. Las cuatro **acusaron de inmediato**: son estos cuatro `ACUSE` en la GUI. Con
> dos, la GUI ya tiene quórum.
>
> Y aunque las cuatro tienen la operación, **respondió una sola**: la titular. Aquí está su
> bitácora: recibió, acusó, encoló, y a la media segunda se supo titular, en el lugar 0 de 4.
> Respondió con `SUM_RES`, un mensaje nuevo con su propio identificador, que lleva el
> identificador de la solicitud original y el resultado.
>
> La respuesta también viajó por broadcast. Las cuatro GUIs la recibieron, pero solo la GUI-1 la
> reconoció como suya, por el identificador de la operación. En esta línea se ve la asociación:
> solicitud tal, respuesta tal. Son identificadores distintos, y la GUI sabe que van juntos.
>
> La operación tarda una media segunda, y casi todo es espera a propósito: es la ventana en la
> que las células se ponen de acuerdo sobre quién responde, sin un coordinador.

---

## ESCENA 6 — Las cuatro operaciones, una desde cada GUI (1:00)

**Qué hacer:** con el mouse, una por GUI (trae cada una al frente):

| GUI | Teclas | Resultado esperado |
|---|---|---|
| GUI-2 | `10` `−` `4` `=` | `6` |
| GUI-3 | `6` `×` `7` `=` | `42` |
| GUI-4 | `7` `÷` `2` `=` | `3.5` |
| GUI-4 | `1` `÷` `0` `=` | `ERROR` y, en rojo, "división entre cero" |

Luego, en la terminal (maximizada):

```powershell
Select-String '\[IGNORA\] (SUB|MUL|DIV)_REQ' logs\GUI-1-*.log | ForEach-Object Line
```

**Se ve:** cada GUI con su resultado y, en cada una, una titular distinta. La terminal muestra las
solicitudes de las otras GUIs que la GUI-1 ignoró: "`SUB_REQ de GUI-2 (…): no es para una GUI`".

**Qué decir:**

> Ahora las cuatro operaciones, cada una desde una GUI distinta. Resta en la GUI-2... seis.
> Multiplicación en la GUI-3... cuarenta y dos. División en la GUI-4... tres punto cinco.
>
> Y una división entre cero. El sistema no se cae: la célula de división responde con un error,
> y ese error es una respuesta válida que viaja igual que un resultado.
>
> Fíjense en quién respondió cada una: la titular cambia de operación en operación. El hash
> reparte el trabajo sin que nadie lo asigne.
>
> Y las GUIs no se ven entre ellas. En "Mis operaciones" cada GUI tiene solo las suyas. Las
> solicitudes de las demás sí les llegan, porque todo es broadcast, pero las ignoran por código.
> Aquí está la bitácora técnica de la GUI-1: ignoró la resta de la GUI-2, la multiplicación de la
> GUI-3 y las divisiones de la GUI-4.

---

## ESCENA 7 — Una sola respuesta por solicitud (1:00) → nota 2 frente a la clase

**Qué hacer:** en la terminal, con el `op` que anotaste en la escena 5 (deja pasar al menos 5 s
desde la operación):

```powershell
$op = 'xxxxxxxx'   # el "op" de 7 + 5 que muestra la GUI-1
Select-String "op $op" logs\SUM-*.log |
  Where-Object Line -match '\[(TITULAR|RESPALDO|LIBERADO|RETIRADA|RES)\]' |
  ForEach-Object { '{0,-8} {1}' -f ($_.Filename -replace '-[0-9a-f]{8}\.log$',''), $_.Line }
```

Y luego el conteo de respuestas por operación:

```powershell
Select-String '\[RES\]' logs\*-N*.log |
  ForEach-Object { ($_.Line -split ' op ')[1].Substring(0,8) } |
  Group-Object | Select-Object Count, Name
```

**Se ve:** las cuatro células de suma: una `TITULAR` con su `RES`, tres `RESPALDO` (rank 1, 2 y 3,
con relevo a los 1.5, 3.0 y 4.5 s) y tres `LIBERADO`. Después, una tabla con **Count = 1** en
cada operación hecha hasta ahora.

> Un respaldo puede salir como `RETIRADA` en lugar de `RESPALDO` + `LIBERADO`: vio la respuesta
> antes de terminar su elección. También es correcto.

**Qué decir:**

> El §9 del enunciado pide evitar que una misma solicitud produzca varias respuestas. Así se
> logra. Cada célula de suma calcula el mismo ranking, un hash de su identificador con el de la
> operación, entre las células que acusaron. Todas llegan a la misma conclusión sin intercambiar
> un solo mensaje extra: una es la titular y responde; las demás quedan como respaldos
> escalonados, cada una con un plazo distinto. Cuando ven la respuesta de la titular, quedan
> liberadas.
>
> Y el conteo: cada operación que hemos hecho tiene **exactamente una** respuesta en todo el
> sistema.
>
> Aquí hay una diferencia con lo que vimos en clase, y la quiero mencionar con todo respeto. En
> clase se planteó que respondieran todas las células y que la GUI tomara la primera. El
> enunciado pide *evitar* las respuestas no deseadas, no solo filtrarlas, y por eso opté por que
> responda una sola. La redundancia no se pierde: está en los respaldos, que responden si la
> titular falla. Y la deduplicación en la GUI que vimos en clase sigue ahí, como última capa.

---

## ESCENA 8 — Titular lenta: relevo y respuesta suprimida (1:45)

**Qué hacer:**

1. En el panel, pon **"retardo ms de los servidores (▶)"** en `4000` y haz clic en **▶** de la
   columna `+` (suma) en la fila **Nodo 3**. Aparece `SUM-N3b` en la lista de procesos:
   **selecciónalo** para ver su bitácora.
2. **Regresa el retardo a `0`** de una vez (si no, el siguiente ▶ también saldría lento).
3. En la **GUI-3**, haz sumas sencillas (`1 + 1`, `2 + 2`, `3 + 3`…) hasta que una tarde **~2 s**
   y su estado diga **"relevo 1 SUM-…"**. Es al azar: con 5 células de suma, la lenta sale
   titular 1 de cada 5 veces en promedio.
4. En la bitácora de `SUM-N3b` (panel) señala `TITULAR` y, unos 4 s después, `SUPRIMIDA`.
5. Al terminar, haz clic en **■** de la columna `+`, fila Nodo 3: tumba la más reciente, que es
   `SUM-N3b`. Así las siguientes sumas no tardan de más.

**Se ve:** en la GUI-3, "relevo 1 SUM-… · acuses 5/2 · ~2000 ms". En la bitácora de `SUM-N3b`:
`[TITULAR] … rank 0 de 5` y luego `[SUPRIMIDA] … ya está resuelta; no envío mi respuesta
(titular)`.

**Qué decir:**

> ¿Qué pasa si la titular se cuelga? Voy a levantar una quinta célula de suma, pero lenta: tarda
> cuatro segundos en calcular. Las GUIs la ven al instante: suma pasa a cinco vivas.
>
> Hago sumas hasta que el hash la elija titular... Ahí está. Esta tardó dos segundos, y quien
> respondió no fue la titular: fue el **relevo 1**. El primer respaldo esperó su plazo, vio que
> nadie había respondido y tomó el relevo.
>
> Lo interesante es lo que pasó después. La titular lenta sí terminó de calcular, a los cuatro
> segundos y medio. Pero antes de publicar volvió a revisar, vio que la operación ya estaba
> resuelta y **suprimió** su respuesta. Resultado: una sola respuesta, aunque la titular seguía
> viva.
>
> Si la titular se muere en lugar de colgarse, pasa lo mismo: responde el relevo. Eso está
> cubierto en las pruebas automatizadas.

---

## ESCENA 9 — Prevención de ciclos con la sonda (1:45)

**Qué hacer:** trae al frente el **Nodo 2** y pon la terminal sobre el área del Nodo 1. Señala
en el encabezado del Nodo 2 los contadores "duplicados descartados" e "ids en el registro
temporal". Luego, uno por uno:

```powershell
py -m sonda --nodo 127.0.0.1:5002 --ttl 1
```

Señala en el Nodo 2: `FWD SONDA_PRUEBA` con destinos "0 nodo(s)" y la fila `TTL`.

```powershell
py -m sonda --nodo 127.0.0.1:5002 --repetir 3
```

Señala en el Nodo 2: un `FWD` y dos `DUP` "de SONDA" con el mismo id.

```powershell
$id = (py -m sonda --nodo 127.0.0.1:5002 | Select-String '^id=').Line.Substring(3)
py -m sonda --nodo 127.0.0.1:5003 --id $id
```

Trae al frente el **Nodo 3** y señala la última fila: `DUP SONDA_PRUEBA … de SONDA`. (El segundo
comando debe ir dentro de los 60 s siguientes al primero).

**Qué decir:**

> Una malla completa está llena de ciclos. Sin defensas, un solo mensaje daría vueltas para
> siempre. Hay cuatro defensas, y para mostrarlas por separado uso una sonda: una herramienta que
> se conecta a un nodo, inyecta un mensaje de prueba que ninguna célula procesa, y termina.
>
> Primera: el TTL. Mando un mensaje con TTL de 1 al Nodo 2. Lo procesó, lo entregó a sus células,
> pero no lo reenvió a ningún nodo: el TTL se agotó ahí.
>
> Segunda: el registro de identificadores. Mando **la misma copia tres veces**. El Nodo 2
> procesó la primera y descartó las otras dos como duplicadas: nunca salieron de ese nodo. Ese
> registro es **temporal**: cada id se recuerda 60 segundos, que es este contador.
>
> Y no es solo el nodo que lo vio entrar. Tomo el identificador de un mensaje que ya circuló y lo
> reinyecto, pero ahora por el Nodo 3. El Nodo 3 también lo reconoce y lo descarta.
>
> Las otras dos defensas se ven en cada operación: un nodo nunca devuelve un mensaje por donde
> llegó ni a un nodo que ya está en la ruta, y cada célula tiene su propio registro de vistos.

---

## ESCENA 10 — Se cae un nodo: failover (1:15)

**Qué hacer:**

1. Acomoda a la vista la **GUI-1** y el **Nodo 2**.
2. En el panel, clic en **■** de la columna **Nodo**, fila **Nodo 1**. La ventana del Nodo 1
   desaparece.
3. Mira la línea de arriba de la GUI-1: pasa a ámbar ("se perdió Nodo 1; buscando otro…") y en
   unos 3 s a verde ("failover → Nodo 2").
4. Señala en el Nodo 2: **"Vecinos: 2"** y **"Células: 10 (2 GUI + 8 servidores)"**.
5. En la GUI-1: `9` `×` `9` `=` → `81`.

**Qué decir:**

> Ahora tumbo un nodo completo, el Nodo 1. El panel lo mata sin avisarle a nadie: es una caída
> real.
>
> Sus cinco células se quedaron sin nodo. Miren la GUI-1: detectó la caída, buscó otro nodo de la
> lista que le dieron al conectarse, y en unos tres segundos se pasó sola al Nodo 2. Lo mismo
> hicieron los cuatro servidores del Nodo 1.
>
> El Nodo 2 ahora tiene dos vecinos y diez células. Y la GUI-1 sigue funcionando: nueve por
> nueve, ochenta y uno.
>
> El failover es más rápido que la caducidad de los latidos, así que ninguna GUI llegó a dar por
> muertos a esos servidores. Por eso ningún nodo es un punto único de falla.
>
> Un detalle: la matriz del panel cuenta las células por el nodo con el que se lanzaron. La que
> dice dónde están colgadas ahora es la ventana del nodo.

---

## ESCENA 11 — Disponibilidad por latidos (1:15) → nota 1 frente a la clase

**Qué hacer:**

1. En el panel, **■** en la columna `÷` de las filas **Nodo 1, Nodo 2 y Nodo 3**. Queda una sola
   célula de división (`DIV-N4`).
2. Espera unos 6 s con la **GUI-2** al frente: "÷ División vivas: 1" con **✗** rojo, el botón `÷`
   en gris y `DESHABILITADA` en el mini log.
3. En la GUI-2 teclea `8` y luego `/` en el teclado: la línea de estado dice en rojo "DIV no
   disponible".
4. Confirma que el retardo del panel está en `0` y haz clic en **▶** de la columna `÷`, fila
   **Nodo 2**: nace `DIV-N2b`. En la GUI-2: `HABILITADA … 2/2 (nueva: DIV-N2b · …)` al instante.
5. En la GUI-2: `8` `÷` `2` `=` → `4`.

*Opcional (20 s):* antes del paso 4, baja "mín. acuses" de División a `1` en la GUI-2: el
operador se habilita con una sola viva. Regrésalo a `2`.

**Qué decir:**

> Cada célula servidor publica un latido cada dos segundos, por broadcast como todo lo demás. Con
> eso, cada GUI sabe en todo momento cuántas células de cada operación están vivas.
>
> Tumbo tres de las cuatro células de división. Seis segundos después, que son tres latidos sin
> noticias, las GUIs las dan por muertas. Queda una viva, y el mínimo de acuses es dos: la GUI
> **deshabilita** la división y lo anota en su mini log. Si intento dividir, me dice que no está
> disponible, en lugar de mandar una solicitud que no podría completarse.
>
> Levanto una célula de división nueva... y en cuanto manda su primer latido, la división se
> habilita otra vez, y la GUI dice cuál célula llegó. Ocho entre dos, cuatro.
>
> Esta es la otra diferencia con lo visto en clase, y también la menciono con respeto. En clase
> se planteó conocer la disponibilidad solo por los acuses. Yo agregué latidos porque así la GUI
> reacciona **antes** de pedir: sabe al instante si una célula aparece o desaparece. Con solo
> acuses, se enteraría hasta que una operación fallara. Los acuses se conservan y también cuentan
> como señal de vida.

---

## ESCENA 12 — Escalar en vivo: un quinto nodo (0:45)

**Qué hacer:**

1. En el panel, **▶** en la columna **Nodo**, fila **Nodo 1**: el Nodo 1 regresa, con 3 vecinos
   y 0 células (las suyas ya viven en el Nodo 2).
2. Clic en **"+ Nodo"**: aparece la fila Nodo 5 en la matriz y su ventana sale encima del
   Nodo 1. Señala **"Vecinos: 4"** y, en el panel, su `--semillas`: un solo nodo.
3. En la GUI-3: `2` `+` `2` `=`. En la tabla de tráfico del Nodo 5: un `FWD SUM_REQ` y tres
   `DUP`.

**Qué decir:**

> El enunciado pide que el protocolo no dependa del número de nodos ni de células. Primero
> regreso el Nodo 1: vuelve a la malla solo, con sus tres vecinos.
>
> Y ahora agrego un **quinto nodo**, con el mismo programa y una sola semilla. En menos de una
> décima de segundo ya está conectado con los otros cuatro. No cambié código ni configuración, y
> no reinicié a nadie.
>
> Hago una suma, y el quinto nodo ya participa: la procesó una vez y descartó tres copias, una por
> cada vecino extra.
>
> Lo mismo pasa con las células: la de suma lenta y la de división nueva que levanté se
> integraron igual, sin avisarle a nadie.

---

## ESCENA 13 — El panel tampoco es punto de falla (0:30)

**Qué hacer:** cierra el panel con su **X**. Al preguntar "¿Detener también todos los
procesos?", contesta **No**. Luego, en la GUI-4: `3` `×` `3` `=` → `9`.

**Qué decir:**

> Por último, cierro el panel y le digo que **no** detenga los procesos.
>
> Las ventanas siguen ahí, y el sistema sigue funcionando: tres por tres, nueve. El panel solo
> lanzaba procesos; el sistema nunca dependió de él.

---

## ESCENA 14 — Pruebas automatizadas (0:30)

**Se ve:** la terminal con la salida de las pruebas que corriste antes de grabar
(`Ran 106 tests in …s` / `OK`).

**Qué decir:**

> El proyecto tiene 106 pruebas automatizadas: unitarias de cada módulo común y de integración
> que levantan el sistema completo dentro del proceso, con una célula espía que cuenta cuántas
> respuestas hay por operación.
>
> Las pruebas encontraron tres errores reales, que están en el reporte. El más interesante: si un
> reintento llegaba a un servidor antes que la solicitud original, por caminos distintos de la
> malla, salía una segunda respuesta. Se corrigió y quedó cubierto con su prueba.

---

## ESCENA 15 — Cierre (0:45)

**Se ve:** las ventanas del sistema, o el diagrama del README.

**Qué decir:**

> Para cerrar, lo principal del diseño:
>
> **Uno.** No hay componente central. Los nodos se encuentran por gossip con una sola semilla, la
> difusión no usa tablas de ruteo, y la titular de cada operación se elige sin coordinador.
>
> **Dos.** Cada solicitud recibe una sola respuesta, con respaldos escalonados por si la titular
> falla, y varias capas más para los casos de borde.
>
> **Tres.** Nada indispensable: se cayó un nodo, se cayeron servidores, se cerró el panel, y el
> sistema siguió funcionando.
>
> Los límites conocidos están documentados en el reporte: los enlaces "medio abiertos" no se
> detectan, no hay autenticación de quien se conecta, y el foliado y las células que levantan
> células quedan para la entrega final.
>
> Gracias.

---

## SI ALGO SE ROMPE EN VIVO

No cortes: explica lo que pasó y recupérate en cámara.

| Qué pasó | Qué decir | Cómo recuperarte |
|---|---|---|
| En la escena 8, la lenta no sale titular tras varias sumas | "Es al azar: el hash la elige una de cada cinco veces" | Sigue sumando; revisa en el panel que `SUM-N3b` esté `vivo` |
| Después de la escena 8, algunas sumas tardan ~2 s | "Es la célula lenta: la está relevando un respaldo" | ■ en `+`, fila Nodo 3 (tumba `SUM-N3b`) |
| `DIV-N2b` salió lenta (escena 11) | — | El retardo no estaba en 0: ■ en `÷` fila Nodo 2, pon 0 y ▶ otra vez |
| Una GUI dice `REINTENTO` o `FALLIDA` | "No llegó el quórum a tiempo; la GUI reintenta sola con el mismo id de operación" | Repite la operación |
| En el panel, un nodo sale `terminado (1)` | "El puerto está ocupado: quedó un proceso de antes" | Cierra todo, corre el comando de limpieza (abajo) y vuelve a levantar |
| Cerraste por error la ventana de un nodo | "Esto es justo una caída real" y explica el failover | ▶ en la columna Nodo de esa fila |
| Una ventana tapa lo que quieres mostrar | — | Clic en la barra de tareas; la lupa (`Win` + `+`) para acercar |

---

## DESPUÉS DE GRABAR

### Limpieza

Con el panel cerrado, los procesos siguen vivos. Para detenerlos todos:

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='py.exe'" |
  Where-Object CommandLine -match ' -m (nodo|servidor|interfaz|panel)( |$)' |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

### Minutos

Ve el video completo y anota **el minuto en que empieza cada escena** en la primera tabla. Si una
evidencia se ve bastante después del inicio de su escena, escribe su minuto exacto en la columna
"Minuto" de la segunda tabla. Si no, déjala vacía y toma el de su escena.

Después corre:

```powershell
py docs/llenar_minutos.py --revisar   # muestra qué minuto va en cada fila, sin escribir
py docs/llenar_minutos.py             # lo escribe en la columna "Video" del §2 del reporte
py docs/md_a_docx.py                  # regenera el .docx
```

El script verifica que las filas de la segunda tabla coincidan con las de la matriz del reporte
(mismo § y mismo requisito, en el mismo orden) y no escribe nada si falta un minuto. Se puede
volver a correr si corriges alguno.

#### Minutos por escena

| Escena | Título | Minuto |
|---|---|---|
| 1 | Presentación | `<mm:ss>` |
| 2 | La arquitectura | `<mm:ss>` |
| 3 | Levantar el sistema | `<mm:ss>` |
| 4 | La malla y el control de conexiones | `<mm:ss>` |
| 5 | Una operación de punta a punta | `<mm:ss>` |
| 6 | Las cuatro operaciones | `<mm:ss>` |
| 7 | Una sola respuesta por solicitud | `<mm:ss>` |
| 8 | Titular lenta: relevo y suprimida | `<mm:ss>` |
| 9 | Prevención de ciclos con la sonda | `<mm:ss>` |
| 10 | Failover | `<mm:ss>` |
| 11 | Disponibilidad por latidos | `<mm:ss>` |
| 12 | Un quinto nodo | `<mm:ss>` |
| 13 | El panel tampoco es punto de falla | `<mm:ss>` |
| 14 | Pruebas automatizadas | `<mm:ss>` |
| 15 | Cierre | `<mm:ss>` |

#### Matriz del reporte

Las filas de la matriz de trazabilidad (§2 del reporte) que se demuestran en el video, en el
mismo orden.

| § | Requisito | Escena | Minuto |
|---|---|---|---|
| 1 | Cualquier lenguaje | 3 | |
| 4 | Suma, resta, multiplicación y división vía Campo de Datos, broadcast y código | 6 | |
| 5 | Célula cliente (GUI): captura, genera la solicitud, recibe la respuesta | 5 | |
| 5 | Célula servidor configurable por servicio | 3 | |
| 5 | Nodo: forma la malla, acepta conexiones, retransmite por broadcast | 4 | |
| 6 | 4 nodos en malla completa | 4 | |
| 6 | 5 células por nodo (20 en total) | 4 | |
| 6 | Sin límite de nodos ni de células; sin cambiar el código | 12 | |
| 7 | Toda solicitud y respuesta lleva Código de Contenido | 5 | |
| 7 | La respuesta es un mensaje nuevo con el id de la solicitud original y el resultado | 5 | |
| 9 | Broadcast por el Campo de Datos | 5 | |
| 9 | Evitar múltiples respuestas no deseadas (estrategia documentada) | 7 | |
| 9 | Respuestas difundidas con su código de respuesta | 5 | |
| 10.1 | Conectar los nodos en malla | 4 | |
| 10.1 | Conectar GUIs y servidores a cada nodo | 4 | |
| 10.1 | Identificar el tipo de entidad y controlar las conexiones activas | 4 | |
| 10.1 | Independiente del número de instancias | 12 | |
| 10.2 | Broadcast entre nodos y células | 5 | |
| 10.2 | Transporta los códigos de solicitud y de respuesta | 5 | |
| 10.2 | Impide la circulación indefinida | 9 | |
| 10.2 | Detecta mensajes ya recibidos | 9 | |
| 10.2 | Asocia la respuesta con su solicitud | 5 | |
| 11 | Registro **temporal** de ids procesados | 9 | |
| 11 | No retransmitir un id repetido | 9 | |
| 11 | La respuesta tiene id propio y conserva el de la solicitud | 5 | |
| 11 | Estrategia contra respuestas duplicadas con varios servidores | 8 | |
| 12 | Flujo general de 10 pasos | 5 | |
| 14 | Nodos 1 a 4 ejecutándose en malla completa | 4 | |
| 14 | Una GUI y un servidor de cada operación por nodo | 4 | |
| 14 | Solicitudes y respuestas con Código de Contenido | 5 | |
| 14 | Asociación correcta solicitud ↔ respuesta | 5 | |
| 14 | Prevención de ciclos y de mensajes duplicados | 9 | |
| 14 | Ejecución correcta de las 4 operaciones | 6 | |
| 15 | Sin nodo central ni punto único de falla | 10 | |
| 15 | Recorrido de los mensajes observable | 5 | |

### Antes de subirlo

- [ ] **El audio se escucha durante todo el video**, no solo al principio.
- [ ] Las 15 escenas tienen su minuto y `py docs/llenar_minutos.py` corrió sin errores.
- [ ] El texto de las ventanas se lee al ver el video en pantalla completa.
- [ ] No se ve información personal, contraseñas ni ventanas ajenas.
- [ ] El video está subido con acceso "cualquiera con el enlace" (YouTube como *no listado*, o
      Drive), y la liga abre en una ventana de incógnito.
- [ ] La liga del video ya está en la portada del reporte (`<LIGA AL VIDEO>`) y el `.docx` se
      regeneró.
