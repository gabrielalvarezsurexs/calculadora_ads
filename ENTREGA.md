# ENTREGA — Segundo Parcial

Hoja de control antes de entregar: los tres entregables que pide el enunciado (§2) y lo que falta
hacer a mano.

## Los 3 entregables

| Entregable | Estado | Dónde / qué falta |
|---|---|---|
| **Reporte técnico** | Escrito | [REPORTE_TECNICO.md](REPORTE_TECNICO.md) y `Reporte_Tecnico_Calculadora_ADS.docx`. Falta llenar la portada y los minutos del video, y regenerar el `.docx` |
| **Video con audio** | Guion listo, **falta grabar** | [GUION_VIDEO.md](GUION_VIDEO.md): 15 escenas, ~16 min |
| **Liga al código fuente** | **Falta publicar** | Commit + push a GitHub |

## Lo que falta que hagas tú

1. **Llenar la portada del reporte.** [REPORTE_TECNICO.md](REPORTE_TECNICO.md) tiene 5
   marcadores: `<NOMBRE COMPLETO>`, `<MATRÍCULA>`, `<GRUPO>`, `<LIGA AL REPOSITORIO>` y
   `<LIGA AL VIDEO>`.

2. **Publicar el repositorio.** El repo local ya existe (`git init` hecho), pero todavía no tiene
   commits: pídeme el commit cuando quieras, o hazlo tú. Luego crea el repo en GitHub y haz push.
   El `.gitignore` ya excluye `logs/`, `__pycache__/` y `.venv/`.

3. **Grabar el video** siguiendo [GUION_VIDEO.md](GUION_VIDEO.md). Antes, corre su checklist de
   preparación (incluye guardar las bitácoras del reporte y correr las pruebas) y **prueba el
   micrófono**: el enunciado pide video *con audio*. Graba la pantalla completa (OBS o Recortes),
   no con la Xbox Game Bar, que graba una sola ventana.

4. **Anotar los minutos.** Al terminar, anota en `GUION_VIDEO.md` el minuto en que empieza cada
   escena (tabla "Minutos por escena") y córrelo al reporte:

   ```powershell
   py docs/llenar_minutos.py --revisar   # muestra qué minuto va en cada fila
   py docs/llenar_minutos.py             # llena la columna "Video" del §2 del reporte
   ```

5. **Subir el video** con acceso "cualquiera con el enlace" (YouTube *no listado* o Drive) y
   comprobar la liga en una ventana de incógnito.

6. **Regenerar el `.docx`** cuando ya no le vayas a mover al reporte (portada y minutos llenos):
   `py docs/md_a_docx.py`. Ábrelo en Word y revisa la portada y la matriz.

7. **Entregar las tres ligas**: reporte, video y repositorio.

## Checklist final antes de entregar

- [ ] La portada del reporte no tiene ningún `<…>` pendiente.
- [ ] La columna "Video" de la matriz (§2) no tiene ningún `<mm:ss>`.
- [ ] `Reporte_Tecnico_Calculadora_ADS.docx` se regeneró después de lo anterior.
- [ ] El video se escucha de principio a fin y su liga abre en incógnito.
- [ ] El repositorio en GitHub es visible para el profesor (público, o con él como colaborador) y
      tiene el último commit, con el `.docx` y las capturas incluidos.
- [ ] La liga del repositorio y la del video en la portada son las mismas que vas a entregar.
- [ ] (Opcional) En el repo publicado, `py -m unittest discover -s tests -t .` sigue en verde.

## Cumplimiento del enunciado

Verificado punto por punto. La matriz completa, con archivo y función de cada requisito, está en
el §2 del reporte técnico.

| § | Requisito | Estado |
|---|---|---|
| 1 | Cualquier lenguaje | Python 3 con librería estándar (se renuncia a los puntos extra de Java) |
| 2 | Reporte, video con audio y liga al código | Reporte escrito; video y liga los hace el usuario |
| 3 | Originalidad | Código propio; la reutilización del primer parcial (mismo autor) está declarada en el §19 del reporte |
| 4 | Las 4 operaciones vía Campo de Datos, broadcast y código | Cumple |
| 5 | Célula cliente (GUI), célula servidor configurable y nodo | Cumple (`interfaz/`, `servidor --servicio`, `nodo/`) |
| 6 | 4 nodos en malla completa con 5 células cada uno; sin límites fijos | Cumple; probado también con un 5º nodo y con células extra |
| 7 | Código de Contenido en toda solicitud y respuesta; la respuesta trae el id original y el resultado | Cumple |
| 8 | Estructura mínima del mensaje | Cumple (sobre documentado en el §6 del reporte) |
| 9 | Broadcast y estrategia contra respuestas múltiples | Cumple (elección por hash entre las que acusaron) |
| 10.1 | Protocolo de conexión: malla, células, tipo de entidad, conexiones activas, N instancias | Cumple |
| 10.2 | Protocolo de comunicación: broadcast, códigos, sin circulación indefinida, detección de repetidos, asociación respuesta–solicitud | Cumple |
| 11 | Id único, registro temporal, no retransmitir repetidos, id propio en la respuesta, estrategia documentada | Cumple |
| 12 | Flujo de 10 pasos | Reproducido con bitácoras reales en el §9 del reporte |
| 13 | Esquema conceptual | §3 del reporte |
| 14 | Evidencias mínimas | Verificadas en vivo; se muestran en el video |
| 15 | Sin nodo central ni punto único de falla; formato documentado; recorrido observable | Cumple |

Estado técnico: **106 pruebas en verde** (unitarias y de integración, ~85 s), `ruff` limpio, y la
verificación en vivo con el panel completa: 4 nodos y 20 células, las 4 operaciones y la división
entre cero con una sola respuesta cada una, failover al tumbar un nodo, operador deshabilitado y
rehabilitado, relevo ante una titular lenta, sondas, un 5º nodo y el sistema funcionando con el
panel cerrado.
