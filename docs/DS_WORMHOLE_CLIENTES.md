# ds-wormhole — parámetros para los clientes

DeepSeek-V4.1-Flash IQ2_XS servido por `strata-dsv41` en `http://<host>:8080` (API OpenAI
`/v1/chat/completions` y Anthropic `/v1/messages`). Escrito el 2026-11-10.

**Reparto (2026-11-10): lo del cliente, en el cliente; lo del motor, en el motor.** El muestreo lo decide cada
cliente en su petición. El servidor no lo fija: solo si una petición no trae `temperature` ni `top_p`, usa los de la
ficha del modelo (1,0 y 1,0, la recomendación oficial; `serve/server.py`, `MODEL_CARD_SAMPLING`). Lo que mande el cliente
gana siempre. El motor no cambia el muestreo por su cuenta.

## Muestreo

| Parámetro | Recomendado | Qué hace aquí | Notas |
|---|---|---|---|
| `temperature` | **1,0** | se aplica en cada token y en la verificación especulativa | recomendación oficial (ficha de DeepSeek, comprobada el 07-11) |
| `top_p` | **1,0** | igual | oficial |
| `top_k` | no mandar, o 64 | el motor guarda como mucho 64 candidatos: 0 o más de 64 = 64 | |
| `min_p` | **0,02** (vibecode hoy); **0,05-0,1** si se quieren menos erratas sueltas | corta lo que esté por debajo de `min_p`·p(primero) | ver abajo |
| `repetition_penalty`, `frequency_penalty`, `presence_penalty` | **no mandar** (1,0 / 0 / 0) | desde el 07-11 se aplican de verdad (antes el motor las ignoraba) | oficial: sin penalizaciones |
| `seed` | opcional | repite el sorteo con la misma semilla | con la penalización de fallos el texto no es repetible entre ejecuciones |
| `max_tokens` | amplio | **cuenta el pensamiento**: con poco margen se corta pensando | contexto de 1M; el servidor avisa con 400 si no cabe |

**`min_p` y las erratas sueltas (medido el 10-11).** A temperatura 1 el modelo a veces sortea un token poco probable.
El contador del motor dice que ~3 % de los tokens son de la cola (menos del 10 % del primero): 1,4 % por debajo del 5 %
y 1,6 % entre el 5 y el 10 %. Entre palabras solo cambia la redacción. Dentro de una palabra sale una errata:
«GNONOME» fue « GN» + «ON» (el 6,6 % de «OME») + «OME», y pasó el `min_p` 0,02. Con 0,1 no habría salido; con 0,05 sí.
Subir `min_p` quita también algo de variedad entre palabras. Es decisión de cada cliente. En el código no se ha visto
ninguna (0 en 57K palabras de Edit/Write de las sesiones del 09-10).

## Pensamiento

| Parámetro | Valores | Notas |
|---|---|---|
| `reasoning_effort` | `low`, `high` (por defecto de la ficha), `max`; `medium` se acepta | `low` piensa mucho menos (más rápido), pero con `low` y sin pensamiento hubo bucles de herramientas en vibecode (05-11) |
| reenviar el razonamiento | **sí** (vibecode: `replayReasoning: true`) | sin él la plantilla deja el pensamiento vacío y el prefijo cambia: más relectura y riesgo de bucles |

Con esfuerzo high el **90 %** de lo que se genera es pensamiento (baterías del 07-09): el tiempo hasta la respuesta es
sobre todo pensar.

## Contexto y reutilización

- **1M de contexto.** Hasta ~600K la velocidad es casi plana; por encima cae un 10-14 %.
- El servidor reutiliza el prefijo de la conversación (99,9 % en sesiones reales). Para no perderlo: mandar el historial
  igual cada turno (sin reescribir mensajes anteriores) y con el razonamiento reenviado.
- **Una conversación en RAM a la vez.** Otra petición (otro cliente, un título, un subagente) la aparca en disco y vuelve
  en ~1 s, **salvo si tiene imágenes**: hoy una conversación con imágenes no se aparca y se relee entera (900K ≈ 50 min).
  Hasta que entre `STRATA_DS4_SLOT_PICS` (escrito el 10-11, sin compilar), no intercalar peticiones con una conversación
  con imágenes.
- Compactar: el resumen se pide con el mismo prefijo, así que sale barato (no se relee). La web solo compacta a mano.

## Herramientas

- Se aceptan las del cliente (`tools`) y las que la conversación ya usó (aunque el turno no las declare).
- Formas de llamada que lee el servidor: DSML de DeepSeek y, a veces, la de Qwen (`<function=…>`).
- **`DS4_TOOL_TRIE`** (motor, escrito el 10-11, sin compilar, apagado): con él, el nombre de una llamada solo puede ser
  uno de los declarados (evita «search_session_transracts», «Vibeccode»). No cambia ninguna salida válida ni necesita
  nada del cliente: el servidor manda la lista de nombres que ya conoce.
- Tiempo de espera del cliente: largo. Claude Code usa `API_TIMEOUT_MS` (no `API_TIMEOUT`); un turno con mucho
  pensamiento pasa de 300 s.

## Por cliente

| Cliente | Dónde se configura | Hoy |
|---|---|---|
| vibecode | sus ajustes (`minP`, `topK`…: `packages/core/src/providers/openai-compat.ts:783`) | `temperature` 1,0, `min_p` 0,02, razonamiento reenviado |
| web ds-wormhole (UI de llama.cpp) | el panel de ajustes del navegador | `deepseek-adapt.js` oculta lo que el motor no tiene (XTC, DRY, `typ_p`, dynatemp) y lo quita del cuerpo |
| Claude Code | `~/claude-deepseek.sh` | esfuerzo high, `API_TIMEOUT_MS=3600000`; usar «accept edits» (el modo auto manda su clasificador al servidor) |

## Lo que no es del cliente

Las claves del motor (`spec`, `dspark_conf`, la penalización de fallos, `SPEC_COST`, el rechequeo de empates, el trie…)
van en el perfil del servidor (`strata-v41-iq2xs-1m-h4d.json`). Se deciden con baterías y no dependen del cliente.
