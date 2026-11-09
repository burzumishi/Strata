"""llama.cpp's resumable streams (tools/server/server-stream.cpp, b12032) for its web UI: a chat completion sent with an
X-Conversation-Id header keeps generating when the page goes away, and its SSE bytes are kept here so the page reloaded
can replay them (GET /v1/stream?conv_id=&from=N), find them (POST /v1/streams/lookup) or stop them (DELETE /v1/stream)."""
from __future__ import annotations

import threading
import time

TTL_S = 3600                   # a finished stream is kept this long (llama.cpp's STREAM_SESSION_TTL_SECONDS: 300; a
                               # reload after a pause in a long agent turn lost the replay, 2026-11-09)
MAX_BYTES = 16 * 1024 * 1024   # a stream's bytes kept at most (llama.cpp keeps 4 MB in a ring; this keeps them whole)


class Session:
    def __init__(self, conv_id: str, cancel: threading.Event):
        self.conv_id, self.cancel = conv_id, cancel
        self.buf = bytearray()
        self.done = False
        self.started = int(time.time())
        self.completed = 0
        self.cond = threading.Condition()

    def append(self, data: bytes) -> None:
        with self.cond:
            if len(self.buf) + len(data) <= MAX_BYTES:
                self.buf += data
            self.cond.notify_all()

    def finish(self) -> None:
        with self.cond:
            self.done = True
            self.completed = int(time.time())
            self.cond.notify_all()

    def info(self) -> dict:
        return {"conversation_id": self.conv_id, "is_done": self.done, "total_bytes": len(self.buf),
                "started_at": self.started, "completed_at": self.completed if self.done else None}

    def read_from(self, offset: int, sink, alive) -> None:
        """Bytes from `offset` to the end, then the live ones until the stream is done or `alive()` is false."""
        while True:
            with self.cond:
                while offset >= len(self.buf) and not self.done:
                    self.cond.wait(1.0)
                    if not alive():
                        return
                chunk = bytes(self.buf[offset:])
                done = self.done
            if chunk:
                if not sink(chunk):
                    return
                offset += len(chunk)
            if done and offset >= len(self.buf):
                return


class Registry:
    def __init__(self):
        self.lock = threading.Lock()
        self.sessions: dict[str, Session] = {}

    def gc(self) -> None:
        now = time.time()
        with self.lock:
            for k in [k for k, s in self.sessions.items() if s.done and now - s.completed > TTL_S]:
                del self.sessions[k]

    def start(self, conv_id: str, cancel: threading.Event) -> Session:
        self.gc()
        s = Session(conv_id, cancel)
        with self.lock:
            old = self.sessions.get(conv_id)
            if old is not None and not old.done:
                old.cancel.set()      # (one conversation, one live generation)
            self.sessions[conv_id] = s
        return s

    def get(self, conv_id: str) -> Session | None:
        self.gc()
        with self.lock:
            return self.sessions.get(conv_id)

    def lookup(self, ids: list[str]) -> list[dict]:
        self.gc()
        out = []
        with self.lock:
            for rid in ids:
                for s in self.sessions.values():
                    if s.conv_id == rid or s.conv_id.startswith(rid + "::"):
                        out.append(s.info())
        return out

    def stop(self, conv_id: str) -> None:
        with self.lock:
            s = self.sessions.pop(conv_id, None)
        if s is not None:
            s.cancel.set()
            s.finish()


class Tee:
    """The handler's wfile while a resumable stream runs: every byte to the session, and to the client while it is
    there (a client gone does not stop the generation; its bytes wait in the session)."""
    def __init__(self, wfile, session: Session):
        self.w, self.s, self.gone = wfile, session, False

    def write(self, data: bytes):
        self.s.append(bytes(data))
        if not self.gone:
            try:
                self.w.write(data)
            except OSError:
                self.gone = True
        return len(data)

    def flush(self):
        if not self.gone:
            try:
                self.w.flush()
            except OSError:
                self.gone = True


REGISTRY = Registry()
