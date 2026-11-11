# ds-wormhole: a Tetris, local against the cloud

<sub><b>English</b> · [Español](DS_WORMHOLE_TETRIS.es.md)</sub>

How far is DeepSeek-V4.1-Flash IQ2_XS on a 64 GB Strix Halo from the model DeepSeek serves in its cloud? One simple
test (2026-11-11): the same prompt, the same agent client and the same settings, once against this machine and once
against the official API. Both runs are single samples at temperature 1, so they are an example, not a benchmark.

## Setup

| | Local | Cloud |
|---|---|---|
| Model | DeepSeek-V4.1-Flash-1017 IQ2_XS (2.25 bpw), `strata-dsv41`, P075a profile, 1M context | `deepseek-flash` on `api.deepseek.com` |
| Machine | Ryzen AI MAX+ 395, Radeon 8060S, 64 GB, Linux | DeepSeek's servers |
| Client | the same agent client (vibecode) with the same tools, including a three.js MCP server and a browser | same |
| Sampling | temperature 1, top_p 0.95, top_k 64, min_p 0.066, thinking on, effort high | same request (the official API probably ignores top_k and min_p) |

The prompt (in Spanish, as it was sent; the file name changed between runs):

```text
tenemos un MCP de threejs configurado crea un Tetris en ~/tetris_local.html con:
- panel principal (tablero para las fichas)
- paneles laterales derecha: panel con contador de puntuación y nivel, panel de visualización próxima pieza, teclas de ayuda
- controlado por las teclas de cursor a los lados, arriba rotar, abajo aumentar velocidad de caída. "Espacio" para "PAUSA" y "COMENZAR" partida.
- todas las piezas con colores distintos y rotación (cursor arriba)
- animación parpadeante para eliminar las lineas completadas
```

In short: a three.js Tetris with a board, a right-hand panel (score and level, next piece, key help), arrow keys,
Space to start and pause, a colour per piece, rotation, and a blinking animation when lines are cleared.

## The sessions

| | Local | Cloud |
|---|---|---|
| Wall time | 55 min | 10 min (about 5.5× faster) |
| Tokens written | 63,751 at ~23 tok/s | ~91,000 including thinking, ~150 tok/s |
| Tool calls | 31 | 99 |
| Checked its own work | yes: start, pause, move, rotate, game over in the browser; a four-line clear in an instrumented copy it deleted afterwards | yes, more thoroughly: it looked at screenshots and fixed washed-out colours by itself |
| Typos | one in the final message ("In Incluye") | none |

## The games

Both games load, run and meet every point of the prompt. The screenshots are taken with a headless Chromium (software
WebGL) driving the keys: start screen, playing, later, paused. (The start banner shows half transparent while playing in
both: that comes from the headless capture, not from the games.)

**Local** ([`tetris_local.html`](ds-wormhole-tetris/tetris_local.html)):

![Local Tetris](ds-wormhole-tetris/local.png)

**Cloud** ([`tetris_cloud.html`](ds-wormhole-tetris/tetris_cloud.html)):

![Cloud Tetris](ds-wormhole-tetris/cloud.png)

## Scores (1-10)

| | Local | Cloud | Notes |
|---|---|---|---|
| Meets the prompt | 9 | 9 | both have every requested part |
| Gameplay | 8 | 9 | both use a 7-piece bag and wall kicks; the cloud also counts lines, scores soft drops and levels up every 10 lines |
| Graphics | **5** | **9** | local: a washed-out light-blue board, pastel pieces, an odd perspective. Cloud: frame, grid, glow, particles, bevelled cubes, true colours |
| Side panel | 7 | 9 | local has no line counter and a small flat preview; the cloud's preview is large and spins |
| Code | 7 | 8.5 | the cloud pools its meshes and handles colour space; the local one is correct but plainer |
| Self-checking | 7 | 9 | |
| Text and typos | 8 | 10 | |
| Speed | 2 | 10 | |
| Cost and privacy | 10 | 6 | local is free and nothing leaves the machine |
| **Overall result quality** | **7** | **9** | |

## What it says

- In logic and code the local model is close: a complete game, no visible bugs, every requirement met.
- The gap is the visual finish, and it has a concrete cause. three.js r128 treats a `0xRRGGBB` colour as linear unless it
  is converted, so colours come out washed out. The cloud model saw it in its own screenshots and fixed it
  (`convertSRGBToLinear`, `sRGBEncoding`); the local one did not notice it, or did not treat it as a problem.
- That looks more like attention to detail than missing ability. It may come from the 2.25 bpw quantization, from the
  miss penalty, or from chance: one sample each. Repeating the test, or running it once on the exact route (no
  substitution, ~6 tok/s), would separate those.
- The local run cost nothing and kept everything on the machine; the cloud was about five times faster.
