# Strata · ds-wormhole

<sub>[English](README.md) · <b>Español</b></sub>

**DeepSeek-V4.1-Flash (763B) con 1M de contexto en un mini PC de 64 GB.** Fork de
[Niko1221/Strata](https://github.com/Niko1221/Strata) adaptado a AMD Strix Halo (Ryzen AI MAX+ 395, Radeon 8060S `gfx1151`,
RDNA 3.5, 64 GB LPDDR5X unificada). La rama de trabajo es `ds-wormhole`.

> Fork personal, no oficial. Todo lo de upstream sigue siendo de Niko1221 y los contribuidores de Strata (MIT, ver
> `LICENSE`); el motor DeepSeek viene de Project Maya (`third_party/project-maya`). El README original de Strata está en
> [`README.strata.md`](README.strata.md) ([español](README.strata.es.md)).

## Qué hace

| | |
|---|---|
| Modelo | DeepSeek-V4.1-Flash-1017 **IQ2_XS** (ISTA-DASLab GSQ-RCO), 40 capas, 384 expertos/capa, Engram IQ4_NL y DSpark Q8_0 |
| Contexto | **1.048.576 tokens** (KV FP4, 890 B/token), visión y herramientas |
| Velocidad (uso real) | **~22-25 t/s** de media en sesiones de agente (2026-11-09: 25,1 t/s de media, mediana 24,8, rango 16,7-37,5; 09-10: 22,1 t/s ponderados) |
| Con contexto largo | por encima de 500K sigue por encima de 20 t/s (sesión de 703K: 24,9 t/s, 872 llamadas a herramientas, 0 errores) |
| Lectura del prompt | 257 t/s de media en sesiones largas; 340-470 t/s con conversaciones cortas |
| Especulación | DSpark: ~2,7 tokens por ronda de verificación, ~124 ms por ronda |
| Memoria | ~3.100 de 15.744 expertos residentes (20 %) cubren el 99,6 % de las peticiones; el carril de CPU sirve el 0,1-0,4 % |

El modelo pesa unos 143 GB de expertos más 111 GB de Engram: no cabe en 64 GB. Funciona porque solo una parte de los
expertos se queda en memoria y los demás se **sustituyen con una penalización medida** (o se leen del SSD sin pasar
por la caché de páginas). Con la ruta exacta, sin sustituciones, va a ~6 t/s; la producción (perfil H4d) va a ~25.

## Qué añade ds-wormhole al motor `strata-dsv41`

Todo es opcional y se activa por variable de entorno; los valores de producción están en
[`configs/ds-wormhole/strata-v41-iq2xs-1m-h4d.example.json`](configs/ds-wormhole/strata-v41-iq2xs-1m-h4d.example.json).

**Memoria unificada (Strix Halo)**
- Almacén de expertos en memoria pinned leída por la GPU en su sitio (`DS4_STORE_GPU`, `DS4_STORE_PINNED`,
  `DS4_STORE_ZC_FRAC`, `DS4_STORE_MAPREAD`), huecos de expertos en host (`DS4_SLOTS_HOST`).
- El «switch» de memoria: el almacén presta sus huecos al prompt (`DS4_STORE_LEND`) y el scratch grande del trozo vive
  en una región pinned prestada (`DS4_CHUNK_LEND`, ~1,5 GB).
- Tabla de embeddings leída del mapeo del modelo, sin copia BF16 (`DS4_EMBED_MAP`, −1,3 GB).

**Calidad con expertos ausentes**
- Penalización de fallos en el router, por capas (`DS4_ROUTE_MISS_PENALTY`, `DS4_ROUTE_PEN_LAYERS`), también en la
  lectura del prompt (`DS4_FLOW_PEN_MAX`, `DS4_PICK_MIN`).
- Rechequeo de casi-empates con la ruta exacta y la regla especulativa (`DS4_TIE_LOG`, `DS4_TIE_RECHECK`, `DS4_TIE_MID`
  para empates dentro de una palabra), con contadores de muestras de la cola.
- Trie de nombres de herramienta: el nombre de una llamada solo puede ser uno de los declarados (`DS4_TOOL_TRIE`).

**Velocidad**
- Elección de cuántos borradores verificar por coste medido de la ronda (`DS4_SPEC_COST`, `DS4_ROUND_LOG`).
- GEMV densas Q5_K con las sumas de activación una vez por bloque en LDS (`DS4_MV_SUMS`, ~10 % menos por ronda,
  resultados idénticos byte a byte).
- Lookahead del router para cualquier formato de experto (`DS4_AHEAD_ANYFMT`), YOCO acotado (`DS4_YOCO`).

**Servidor y clientes**
- Conversaciones aparcadas en disco, también con imágenes (`STRATA_DS4_SLOT_PICS`): vuelven en ~1 s sin recodificar.
- Penalizaciones de repetición/frecuencia/presencia con la semántica de llama.cpp.
- La web de llama.cpp (b12032) como interfaz, con herramientas (`web_search`, `fetch_url`, ficheros), MCP, adjuntos e
  imágenes: [`docs/DS_WORMHOLE_WEB.md`](docs/DS_WORMHOLE_WEB.md).
- Llamadas DSML leídas como las lee `deepseek-recipe`; API OpenAI y Anthropic (Claude Code).
- Parámetros para los clientes (el muestreo es del cliente, no del servidor):
  [`docs/DS_WORMHOLE_CLIENTES.md`](docs/DS_WORMHOLE_CLIENTES.md).

## Requisitos y compilación

- Linux (probado en Ubuntu 26.04, kernel 7.0), ROCm 7.2.4, CMake + Ninja.
- BIOS con el carve-out de la iGPU al mínimo (UMA 2 GB) y GTT grande por el arranque del kernel:
  `amdgpu.gttsize=57344 ttm.pages_limit=14680064 amdgpu.vm_fragment_size=9 iommu=pt`. **No** desactivar CWSR
  (`amdgpu.cwsr_enable=0` provoca reinicios de la GPU). THP sin defrag síncrono.
- Unos 300 GB de disco para el modelo, el Engram, el borrador y la visión.

```bash
cmake -S . -B build-dsv41-hip -G Ninja -DCMAKE_BUILD_TYPE=Release -DSTRATA_ENABLE_HIP=ON -DSTRATA_ENABLE_CUDA=OFF \
  -DSTRATA_BUILD_TESTS=ON -DCMAKE_HIP_ARCHITECTURES=gfx1151 \
  -DCMAKE_HIP_COMPILER=/opt/rocm-7.2.4/llvm/bin/clang++ -DCMAKE_PREFIX_PATH=/opt/rocm-7.2.4
cmake --build build-dsv41-hip --target strata-dsv41 -j12
```

Arranque (servidor Python de Strata con el perfil de ejemplo, rellenando `<STRATA>`, `<MODELS>` y `<DATA>`):

```bash
.venv/bin/python serve/server.py --engine strata --config strata-v41-iq2xs-1m-h4d.json --host 0.0.0.0 --port 8080
```

Pararlo con SIGTERM para que guarde la conversación en curso.

## Qwen en Strix Halo

La rama también lleva el port de los motores de Qwen a `gfx1151` hecho antes (octubre de 2026): expertos MXFP4,
arena de memoria unificada, MTP nativo Q4_0/Q8_0, visión en HIP, aparcado de conversaciones en disco
(`--conversation-disk-dir`) y el motor `strata-q36` con atención WMMA de prompt, KV int8, YaRN y los 27B densos.
Son los commits `local:` del historial; [`docs/STRIX_HALO.md`](docs/STRIX_HALO.md) es la guía de upstream para esta
máquina.

## Estado

Trabajo en curso. Los cambios se miden con baterías de tareas reales (velocidad, validez y erratas), no con
benchmarks cortos, y no se recuantiza para ganar velocidad. Las mejoras de upstream posteriores a v0.2.9 se traen por
cherry-pick en ramas aparte (`ds-wormhole-up`).
