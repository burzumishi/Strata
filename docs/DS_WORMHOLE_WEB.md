# ds-wormhole: the web UI

DeepSeek-V4.1-Flash IQ2_XS on `strata-dsv41` serves **llama.cpp's web UI (b12032)** at `/`:
`serve/web/llamacpp/`, served by `_llama_ui()` in `serve/server.py`. It replaces the old Strata page
(`serve/web/`), which is still in the tree for the monitor and image generation.

## Server fixes (commit `1c787bc7`)

- `/tools`: a string `error` and a 400 for an empty name (the UI printed `[object Object]` and ran the
  model's call with `{}`); `/models/unload` answers 200.
- SSE: an error also goes out as a `choices[0].delta.content` chunk (the UI only reads `choices`), and a
  stream replay backs `from` up to an SSE event boundary.
- `sw.js`: a self-unregistering worker; the build's worker cached `/v1/*`, `/props`, `/models`, `/tools`
  and `/slots` for 24 h. Every API answer is now `Cache-Control: no-store`.
- `/props`: `max_tokens` (the UI syncs that, not `n_predict`); `/models/sse`: the first `model_status`
  event; pre-encode: `prompt_tokens` and `timings`.
- `n_predict > 0` is `max_tokens`; live timings also on `tool_start`/`tool_args`; undeclared tool calls
  are named in the text, not only in `strata_rejected_tool_calls`.
- gzip for the UI's text assets; the image model is no longer listed as a chat model; a finished stream
  is kept 3600 s.

These live in `serve/server.py` and `serve/streams.py`: they apply when the Python server is restarted.

## DeepSeek adaptation (commit `d93fe3be`)

`serve/web/llamacpp/deepseek-adapt.js`, loaded from `index.html` before the bundle:

- **Hides 11 fields** the engine does not implement: Dynamic temperature range/exponent, XTC
  probability/threshold, Typical P, Samplers, Backend sampling, DRY multiplier/base/allowed length/
  penalty last N.
- **Hides 2 router settings**: Discover Models and the Hugging Face Hub API (one model, nothing to
  download).
- **Keeps**: Temperature, Top K, Top P, Min P, Max tokens, Repeat last N, Repeat penalty,
  Presence/Frequency penalty, API Key, System Message, Tools, MCP, Agentic, Developer (custom JSON/CSS),
  Continue and reasoning.
- It wraps `window.fetch` and removes those keys from `/v1/chat/completions` bodies; a `MutationObserver`
  hides each field (`label` + input + help). `window.__deepseekAdapt = {dropped, hidden}` exposes the
  state for debugging.
- `index.html` is generated: re-apply the `<script src="./deepseek-adapt.js">` after regenerating the
  build (the `.js` is kept). No server restart is needed.

## End-to-end test (2026-11-09)

The UI was served from a temporary local harness (not committed) and driven in a browser against
DeepSeek's cloud API. Task:

> Use `web_search` for "capital de Australia", `fetch_url` on
> `https://es.wikipedia.org/wiki/Camberra`, write a two-line summary to `/tmp/ds-tools-test.txt` with
> `write_file`, and answer with the capital and the demonym.

Result: the model ran **web_search → fetch_url → write_file → read_file**, verified the file, and
answered "Camberra / camberrano". The file was 375 bytes. The UI rendered each tool block, the
reasoning, and the final answer.

Errors found and what they were:

| Symptom | Cause | Action |
|---|---|---|
| `Stream lookup returned a non-array response` | The temporary harness answered `{"streams": []}`; the UI expects the list itself (`REGISTRY.lookup` returns one) | Harness fixed to `[]`; the server already returns the list |
| `SW registration error: 404` | The harness does not serve `sw.js` | Expected in the harness; the server serves the self-unregistering worker after the restart |
| `ResizeObserver loop completed...` | Browser layout warning | Benign |

No product error surfaced: tools, MCP panel, reasoning, Continue, the sampling page and the adapted
Settings all behaved.

## Pending

- Restart the Python server once to load `1c787bc7` (the static adaptation is already live).
- The old Strata page's **monitor** (GPU/VRAM/temperature, request table) and **image generation** have
  no equivalent in llama.cpp's UI; keep them as separate pages.
- The UI is English-only; the old page had 9 languages.
