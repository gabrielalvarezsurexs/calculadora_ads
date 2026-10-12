"""Todas las constantes de tiempo, TTL y tamaños del sistema, en un solo lugar.

Regla del proyecto: el resto del código las lee como ``config.X`` en el momento
de usarlas, NUNCA con ``from comun.config import X``. Así las pruebas pueden
acortar los tiempos con ``mock.patch.object(config, "LATIDO", 0.2)`` y el cambio
se ve en todos los módulos sin reiniciar nada.

Los tiempos están en segundos.
"""

# --- Broadcast y prevención de ciclos (§9, §11) -----------------------------
TTL_INICIAL = 8           # con lo que publica una célula; debe ser >= diámetro de la red
TTL_MAX = 16              # tope: un TTL mayor que llegue por la red se recorta
VISTOS_VIGENCIA = 60.0    # cuánto recuerda el registro temporal un id ya procesado
VISTOS_MAX = 100_000      # tope de ids en el registro (se olvidan los más viejos)

# --- Latidos y disponibilidad -----------------------------------------------
LATIDO = 2.0              # cada cuánto emite SRV_LAT un servidor
LATIDO_CADUCIDAD = 6.0    # sin latido ni acuse en este tiempo, la célula se da por muerta

# --- Acuses, elección y plazos de la GUI -----------------------------------
VENTANA_ACUSES = 1.5      # sin quórum en este tiempo, la GUI reintenta
VENTANA_ELECCION = 0.5    # lo que espera un servidor para juntar acuses antes de elegir
RELEVO = 1.5              # separación entre respaldos escalonados (rank r espera r·RELEVO)
MARGEN_RESULTADO = 2.0    # holgura extra del plazo de resultado en la GUI
MAX_INTENTOS = 3
ACUSES_MIN_DEFECTO = 2

# --- Conexión ---------------------------------------------------------------
HOLA_TIMEOUT = 5.0        # una conexión entrante que no se presenta en este tiempo se cierra
BIENVENIDA_TIMEOUT = 3.0  # lo que espera quien marca a que el nodo lo acepte
CONECTAR_TIMEOUT = 3.0    # connect() TCP
BACKOFF_MIN = 1.0
BACKOFF_MAX = 8.0
SUPERVISOR = 2.0          # cada cuánto el nodo revisa qué endpoints conocidos le faltan
REINTENTOS_MISMO_NODO = 2 # failover: intentos con el nodo original antes de rotar
# connect() de esos reintentos. En Windows, marcar a un puerto cerrado tarda ~2 s
# en devolver el rechazo; sin este tope, el failover tardaría ~6 s en vez de ~3.
REINTENTO_TIMEOUT = 0.5

# --- Transporte -------------------------------------------------------------
MAX_LINEA = 64 * 1024     # una línea NDJSON más larga se descarta
COLA_ENLACE_MAX = 5_000   # mensajes pendientes por enlace antes de darlo por LENTO

# --- Servidor ---------------------------------------------------------------
RONDAS_VIGENCIA = 120.0   # rondas más viejas que esto se purgan

# --- Presentación -----------------------------------------------------------
# Códigos que NO se escriben en consola (sí en archivo). El nodo no interpreta
# el catálogo: esto es solo un filtro de ruido para la bitácora.
CODIGOS_SILENCIOSOS = ("SRV_LAT",)
