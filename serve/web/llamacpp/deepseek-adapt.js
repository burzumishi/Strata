/*
 * DeepSeek adaptation for llama.cpp's web UI (ds-wormhole, 2026-11-09).
 *
 * The engine is DeepSeek-V4.1-Flash: it has temperature, top_k, top_p, min_p, the
 * repetition/presence/frequency penalties, seed and max_tokens. It has no XTC, DRY,
 * typical-p, dynamic temperature, sampler order or backend sampling, and this server
 * has no second model to discover or download. The build shows those controls anyway;
 * this layer hides them and keeps their keys out of the request body, so the UI matches
 * the engine instead of the other way round.
 *
 * Loaded from index.html before the bundle. Re-apply it if the UI build is regenerated.
 */
(() => {
  "use strict";

  const DROP = [
    "samplers", "backend_sampling",
    "xtc_probability", "xtc_threshold",
    "typ_p", "dynatemp_range", "dynatemp_exponent",
    "dry_multiplier", "dry_base", "dry_allowed_length", "dry_penalty_last_n",
  ];

  const HIDE = [
    "Dynamic temperature range", "Dynamic temperature exponent",
    "XTC probability", "XTC threshold", "Typical P",
    "Samplers", "Backend sampling",
    "DRY multiplier", "DRY base", "DRY allowed length", "DRY penalty last N",
    // router controls: one model, loaded at start, nothing to discover or download
    // (the API Key field stays: it is useful if the server is started with one)
    "Enable Discover Models", "Use the Hugging Face Hub API",
  ];

  // The image model is in /v1/models for its own endpoint, not for chat: the picker must not offer it.
  const IMAGE_MODELS = ["qwen-image"];

  const debug = (window.__deepseekAdapt = { dropped: [], hidden: 0 });

  // 1) Do not send what the engine does not implement (the server ignores it anyway).
  const originalFetch = window.fetch;
  window.fetch = function (input, init) {
    try {
      const url = typeof input === "string" ? input : (input && input.url) || "";
      if (init && typeof init.body === "string" && url.includes("/v1/chat/completions")) {
        const body = JSON.parse(init.body);
        const present = DROP.filter((key) => key in body);
        if (present.length) {
          for (const key of present) delete body[key];
          debug.dropped = present;
          init = { ...init, body: JSON.stringify(body) };
        }
      }
    } catch (_) {
      // not a JSON body: leave it as it is
    }
    return originalFetch.call(this, input, init);
  };

  // 2) Hide the controls, field by field (label + input + help live in one div).
  const fieldOf = (label) => {
    let node = label.parentElement;
    for (let i = 0; i < 5 && node; i++) {
      if (node.querySelector("input,textarea,select,[role=switch],[role=checkbox]")) return node;
      node = node.parentElement;
    }
    return label.parentElement;
  };

  const hide = () => {
    let hidden = 0;
    for (const label of document.querySelectorAll("label")) {
      const text = (label.textContent || "").trim();
      if (!HIDE.includes(text)) continue;
      const field = fieldOf(label);
      if (!field) continue;
      if (field.style.display !== "none") field.style.display = "none";
      hidden++;
    }
    // ... and the image model, wherever the model picker lists it (role=option, a button or a list row)
    for (const el of document.querySelectorAll('[role="option"], button, li, a')) {
      const text = (el.textContent || "").trim();
      if (!text || text.length > 200) continue;
      if (!IMAGE_MODELS.some((name) => text.toLowerCase().includes(name))) continue;
      const option = el.closest('[role="option"]') || el;
      if (option.style.display !== "none") option.style.display = "none";
      hidden++;
    }
    debug.hidden = hidden;
  };

  let pending = false;
  const schedule = () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      hide();
    });
  };

  const start = () => {
    hide();
    new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
