"""llama.cpp's built-in server tools (tools/server/server-tools.cpp, b12032) for its web UI: same names, parameters and
answers, so the page's tools panel works against Strata. Off unless the server is started with --tools NAME,NAME|all
(they read, write and run things on this machine for whoever reaches the port).

read_file, file_glob_search, grep_search, exec_shell_command, write_file, edit_file, get_info."""
from __future__ import annotations

import base64
import fnmatch
import os
import re
import subprocess
from pathlib import Path

READ_FILE_MAX = 16 * 1024
READ_FILE_MAX_BASE64 = 32 * 1024 * 1024   # (llama.cpp SERVER_TOOL_READ_FILE_MAX_SIZE_BASE64)
SEARCH_MAX = 100
GREP_MAX = 100
EXEC_MAX_OUTPUT = 16 * 1024
EXEC_MAX_TIMEOUT = 60
JUNK = {".git", "node_modules", "build", "dist", "__pycache__", ".venv", "venv", ".cache", "target", ".idea", ".vscode"}


def _fn(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc,
                                             "parameters": {"type": "object", "properties": props, "required": required}}}


DEFS = {
    "read_file": ("Read file", False, False, _fn(
        "read_file", "Read the contents of a file. Optionally specify a 1-based line range. "
                     "If append_loc is true, each line is prefixed with its line number (e.g. \"1→...\").",
        {"path": {"type": "string", "description": "Path to the file"},
         "start_line": {"type": "integer", "description": "First line to read, 1-based (default: 1)"},
         "end_line": {"type": "integer", "description": "Last line to read, 1-based inclusive (default: end of file)"},
         "append_loc": {"type": "boolean", "description": "Prefix each line with its line number"}}, ["path"])),
    "file_glob_search": ("File search", False, False, _fn(
        "file_glob_search",
        "Recursively search for files matching a glob pattern under a directory. Automatically skips files ignored by "
        ".gitignore (when the directory is inside a git repo) and common junk directories (.git, node_modules, build, dist, "
        "etc.) otherwise. A pattern with no '/' (e.g. \"*.cpp\") matches the file's basename at any depth. A pattern "
        "containing '/' matches the full relative path; unless already anchored with \"**/\" or a leading '/', it is "
        "automatically prefixed with \"**/\". Use type=\"dir\" or \"all\" to also list directories; directory entries are "
        "suffixed with '/' in the output. Note: directory listings do not apply .gitignore filtering.",
        {"path": {"type": "string", "description": "Base directory to search in"},
         "include": {"type": "string", "description": "Glob pattern for files to include (e.g. \"*.cpp\" or \"src/**/*.cpp\"). Default: **"},
         "exclude": {"type": "string", "description": "Glob pattern for files to exclude"},
         "type": {"type": "string", "description": "Entry type to return: \"file\" (default), \"dir\" or \"all\""},
         "max_depth": {"type": "integer", "description": "Maximum depth to descend into subdirectories (default: 0 = unlimited; 1 = direct children only)"},
         "limit": {"type": "integer", "description": f"Maximum number of results to return, capped at {SEARCH_MAX} (default {SEARCH_MAX})"}},
        ["path"])),
    "grep_search": ("Grep search", False, False, _fn(
        "grep_search",
        "Search for a pattern in files under a path. Returns matching lines with file paths (and, unless searching a "
        "single file, paths relative to the given directory). Automatically skips files ignored by .gitignore (when the "
        "directory is inside a git repo) and common junk directories (.git, node_modules, build, dist, etc.) otherwise. "
        "include/exclude: a pattern with no '/' matches the basename at any depth; a pattern containing '/' matches the "
        "full relative path (auto-anchored with \"**/\" unless already anchored).",
        {"path": {"type": "string", "description": "File or directory to search in"},
         "pattern": {"type": "string", "description": "Pattern to search for (regular expression unless literal is true)"},
         "include": {"type": "string", "description": "Glob pattern to filter files (default: **)"},
         "exclude": {"type": "string", "description": "Glob pattern to exclude files"},
         "return_line_numbers": {"type": "boolean", "description": "If true, include line numbers in results"},
         "literal": {"type": "boolean", "description": "Treat pattern as a literal string instead of a regular expression (default: false)"},
         "ignore_case": {"type": "boolean", "description": "Case-insensitive search (default: false)"},
         "context_lines": {"type": "integer", "description": "Number of lines of context to show before and after each match (default: 0)"}},
        ["path", "pattern"])),
    "exec_shell_command": ("Execute shell command", True, True, _fn(
        "exec_shell_command", "Execute a shell command and return its output (stdout and stderr combined).",
        {"command": {"type": "string", "description": "Shell command to execute"},
         "timeout": {"type": "integer", "description": f"Timeout in seconds (default 10, max {EXEC_MAX_TIMEOUT})"},
         "max_output_size": {"type": "integer", "description": f"Maximum output size in bytes (default {EXEC_MAX_OUTPUT})"}},
        ["command"])),
    "write_file": ("Write file", True, False, _fn(
        "write_file", "Write content to a file, creating it (including parent directories) if it does not exist. May use "
                      "with edit_file for more complex edits.",
        {"path": {"type": "string", "description": "Path of the file to write"},
         "content": {"type": "string", "description": "Content to write"}}, ["path", "content"])),
    "edit_file": ("Edit file", True, False, _fn(
        "edit_file", "Edit a file using exact text replacement. Each edits[].old_text must be unique in the file and is "
                     "matched against the original content, not incrementally. Merge nearby changes into one edit instead "
                     "of overlapping edits. Use write_file to replace the whole file.",
        {"path": {"type": "string", "description": "Path to the file to edit"},
         "edits": {"type": "array", "description": "One or more exact text replacements to apply",
                   "items": {"type": "object", "properties": {
                       "old_text": {"type": "string", "description": "Exact text to find; must be unique in the file and must not overlap with other edits"},
                       "new_text": {"type": "string", "description": "Text to replace old_text with"}},
                       "required": ["old_text", "new_text"]}}}, ["path", "edits"])),
    "get_info": ("Get Runtime Info", False, True, _fn(
        "get_info", "Returns runtime info: the OS name/version and the current working directory", {}, [])),
}
USES_CWD = {"file_glob_search": False, "grep_search": False, "exec_shell_command": True, "get_info": True,
            "read_file": False, "write_file": False, "edit_file": False}


class LlamaTools:
    def __init__(self, enabled: list[str], cwd: str | None = None):
        names = set(enabled)
        self.names = [n for n in DEFS if n in names or "all" in names]
        self.cwd = cwd or os.getcwd()

    def listing(self) -> list[dict]:
        out = []
        for n in self.names:
            disp, write, _stream, d = DEFS[n]
            out.append({"display_name": disp, "tool": n, "type": "server", "permissions": {"write": write},
                        "uses_cwd": USES_CWD[n], "definition": d})
        return out

    def has(self, name: str) -> bool:
        return name in self.names

    # ---- helpers
    def _path(self, p: str, cwd: str | None) -> Path:
        q = Path(os.path.expanduser(p))
        return q if q.is_absolute() else Path(cwd or self.cwd) / q

    @staticmethod
    def _norm_glob(pat: str | None) -> str | None:
        if not pat:
            return None
        if "/" in pat and not pat.startswith("**/") and not pat.startswith("/"):
            return "**/" + pat
        return pat.lstrip("/")

    @staticmethod
    def _braces(pat: str) -> list[str]:
        """{a,b} alternatives expanded (llama.cpp's glob has none; models write "**/*.{js,json}" anyway and got no match)"""
        m = re.search(r"\{([^{}]*)\}", pat)
        if not m:
            return [pat]
        out = []
        for alt in m.group(1).split(","):
            out += LlamaTools._braces(pat[:m.start()] + alt + pat[m.end():])
        return out

    @staticmethod
    def _match(rel: str, pat: str | None) -> bool:
        if not pat:
            return True
        if "{" in pat:
            return any(LlamaTools._match(rel, p) for p in LlamaTools._braces(pat))
        if "/" not in pat:
            return fnmatch.fnmatch(rel.rsplit("/", 1)[-1], pat)
        if fnmatch.fnmatch(rel, pat):
            return True
        return pat.startswith("**/") and fnmatch.fnmatch(rel, pat[3:])

    def _walk(self, base: Path, want_dirs: bool, want_files: bool, max_depth: int):
        """(relative path, is_dir) under base: git ls-files when base is in a git repo (files), else a walk skipping junk"""
        if want_files and not want_dirs:
            try:
                r = subprocess.run(["git", "-C", str(base), "ls-files", "-co", "--exclude-standard"], capture_output=True,
                                   text=True, timeout=15)
                if r.returncode == 0:
                    for rel in r.stdout.splitlines():
                        if max_depth and rel.count("/") + 1 > max_depth:
                            continue
                        yield rel, False
                    return
            except (OSError, subprocess.TimeoutExpired):
                pass
        for root, dirs, files in os.walk(base):
            rroot = os.path.relpath(root, base)
            depth = 0 if rroot == "." else rroot.count(os.sep) + 1
            dirs[:] = [d for d in dirs if d not in JUNK]
            if max_depth and depth + 1 > max_depth:
                dirs[:] = []
            for d in (dirs if want_dirs else []):
                yield (d if rroot == "." else f"{rroot}/{d}"), True
            for f in (files if want_files else []):
                if not max_depth or depth + 1 <= max_depth:
                    yield (f if rroot == "." else f"{rroot}/{f}"), False

    # ---- the tools
    def call(self, name: str, p: dict, cwd: str | None = None, on_chunk=None) -> dict:
        try:
            return getattr(self, "t_" + name)(p, cwd, on_chunk)
        except KeyError as e:
            return {"error": f"missing parameter: {e}"}
        except Exception as e:   # (the UI shows the text)
            return {"error": f"{type(e).__name__}: {e}"}

    def t_read_file(self, p, cwd, _):
        path = self._path(p["path"], cwd)
        start, end, loc = int(p.get("start_line") or 1), int(p.get("end_line") or -1), bool(p.get("append_loc"))
        if not path.is_file():
            return {"error": f"cannot stat file: {p['path']}"}
        if p.get("resp_type") == "base64":   # (the x-resp-type header, as llama.cpp's server: read_media's bytes, 32 MB at most)
            n = path.stat().st_size
            if n > READ_FILE_MAX_BASE64:
                return {"error": f"file too large ({n} bytes, max {READ_FILE_MAX_BASE64})"}
            data = path.read_bytes()
            return {"base64": base64.b64encode(data).decode("ascii"), "size_bytes": len(data)}
        if path.stat().st_size > READ_FILE_MAX and end == -1:
            return {"error": f"file too large ({path.stat().st_size} bytes, max {READ_FILE_MAX}). Use start_line/end_line to read a portion."}
        out = []
        size = 0
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f, 1):
                if n < start:
                    continue
                if end != -1 and n > end:
                    break
                line = line.rstrip("\n")
                s = (f"{n}→{line}\n" if loc else line + "\n")
                if size + len(s) > READ_FILE_MAX:
                    out.append("[output truncated]")
                    break
                out.append(s)
                size += len(s)
        return {"plain_text_response": "".join(out)}

    def t_file_glob_search(self, p, cwd, _):
        base = self._path(p["path"], cwd)
        kind = p.get("type") or "file"
        if kind not in ("file", "dir", "all"):
            return {"error": f"invalid type: {kind} (expected \"file\", \"dir\" or \"all\")"}
        limit = int(p.get("limit") or SEARCH_MAX)
        if limit < 1:
            return {"error": f"invalid limit: {limit} (expected 1 or more)"}
        limit = min(limit, SEARCH_MAX)
        if not base.is_dir():
            return {"error": f"not a directory: {p['path']}"}
        inc, exc = self._norm_glob(p.get("include") or "**"), self._norm_glob(p.get("exclude"))
        matches = []
        for rel, isdir in self._walk(base, kind in ("dir", "all"), kind in ("file", "all"), int(p.get("max_depth") or 0)):
            if inc not in (None, "**") and not self._match(rel, inc):
                continue
            if exc and self._match(rel, exc):
                continue
            matches.append((rel, isdir))
            if len(matches) > 10000:   # (a time budget of sorts: a listing of / would go on for long)
                break
        shown = matches[:limit]
        # llama.cpp's answer: the text the model reads, and entries {path, type} + an absolute base for the web UI's picker
        text = "".join(r + ("/" if d else "") + "\n" for r, d in shown) + f"\n---\nTotal matches: {len(matches)}\n"
        if len(matches) > limit:
            text += (f"[{limit} results limit reached ({len(matches)} total matches). Refine the glob pattern to narrow "
                     "the search.]\n")
        return {"plain_text_response": text, "entries": [{"path": r, "type": "dir" if d else "file"} for r, d in shown],
                "base": str(base.resolve())}

    def t_grep_search(self, p, cwd, _):
        base = self._path(p["path"], cwd)
        flags = re.IGNORECASE if p.get("ignore_case") else 0
        try:
            rx = re.compile(re.escape(p["pattern"]) if p.get("literal") else p["pattern"], flags)
        except re.error as e:
            return {"error": f"invalid regex: {e}"}
        if not base.exists():
            return {"error": f"path does not exist: {p['path']}"}
        ctx, nums = int(p.get("context_lines") or 0), bool(p.get("return_line_numbers"))
        inc, exc = self._norm_glob(p.get("include")), self._norm_glob(p.get("exclude"))
        files = [(base, base.name)] if base.is_file() else \
            [(base / rel, rel) for rel, _d in self._walk(base, False, True, 0)
             if (not inc or inc == "**" or self._match(rel, inc)) and not (exc and self._match(rel, exc))]
        out, hits = [], 0
        for f, rel in files:
            try:
                lines = f.read_text(encoding="utf-8", errors="strict").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(lines):
                if not rx.search(line):
                    continue
                for j in range(max(0, i - ctx), min(len(lines), i + ctx + 1)):
                    out.append(f"{rel}:{j + 1}:{lines[j]}" if nums else f"{rel}:{lines[j]}")
                hits += 1
                if hits >= GREP_MAX:
                    out.append(f"[results truncated at {GREP_MAX}]")
                    return {"plain_text_response": "\n".join(out)}
        return {"plain_text_response": "\n".join(out) if out else "no matches"}

    def t_exec_shell_command(self, p, cwd, on_chunk):
        timeout = min(int(p.get("timeout") or 10), EXEC_MAX_TIMEOUT)
        cap = min(int(p.get("max_output_size") or EXEC_MAX_OUTPUT), EXEC_MAX_OUTPUT)
        proc = subprocess.Popen(["sh", "-c", p["command"]], cwd=cwd or self.cwd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        out, timed_out = b"", False
        try:
            import time
            end = time.monotonic() + timeout
            os.set_blocking(proc.stdout.fileno(), False)
            while True:
                chunk = proc.stdout.read(4096) or b""
                if chunk:
                    room = cap - len(out)
                    if room > 0:
                        out += chunk[:room]
                        if on_chunk:
                            on_chunk(chunk[:room].decode("utf-8", "replace"))
                elif proc.poll() is not None:
                    break
                else:
                    time.sleep(0.02)
                if time.monotonic() > end:
                    proc.kill()
                    timed_out = True
                    break
        finally:
            proc.wait()
        tail = f"\n[exit code: {proc.returncode}]" + (" [exit due to timed out]" if timed_out else "")
        if on_chunk:
            on_chunk(tail)
            return {}
        return {"plain_text_response": out.decode("utf-8", "replace") + tail}

    def t_write_file(self, p, cwd, _):
        path = self._path(p["path"], cwd)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = p["content"]
        path.write_text(data, encoding="utf-8")
        return {"result": "file written successfully", "path": str(path), "bytes": len(data.encode("utf-8"))}

    def t_edit_file(self, p, cwd, _):
        path = self._path(p["path"], cwd)
        edits = p.get("edits")
        if not isinstance(edits, list) or not edits:
            return {"error": "\"edits\" must be a non-empty array"}
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return {"error": f"failed to open file: {p['path']}"}
        spans = []
        for i, e in enumerate(edits):
            old = e.get("old_text") or ""
            if not old:
                return {"error": f"edits[{i}].old_text must not be empty"}
            n = text.count(old)
            if n != 1:
                return {"error": f"edits[{i}].old_text {'not found' if n == 0 else f'found {n} times (must be unique)'}"}
            a = text.index(old)
            spans.append((a, a + len(old), e.get("new_text", ""), i))
        spans.sort()
        for (a1, b1, _, i1), (a2, _b2, _, i2) in zip(spans, spans[1:]):
            if a2 < b1:
                return {"error": f"edits[{i1}] and edits[{i2}] overlap"}
        out, at = [], 0
        for a, b, new, _ in spans:
            out.append(text[at:a] + new)
            at = b
        new_text = "".join(out) + text[at:]
        if new_text == text:
            return {"error": "no changes made: the replacement(s) produced identical content"}
        path.write_text(new_text, encoding="utf-8")
        return {"result": "file edited successfully", "path": str(path), "edits_applied": len(spans)}

    def t_get_info(self, p, cwd, _):
        try:
            r = subprocess.run(["uname", "-a"], capture_output=True, text=True, timeout=5)
            os_info = r.stdout.strip() if r.returncode == 0 else "unknown"
        except (OSError, subprocess.TimeoutExpired):
            os_info = "unknown"
        return {"os": os_info, "cwd": cwd or self.cwd}
