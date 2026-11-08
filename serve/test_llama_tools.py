"""llama.cpp's built-in tools for its web UI (serve/llama_tools.py): the arguments a model wraps, the output of a command."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from serve.llama_tools import LlamaTools, unwrap_params  # noqa: E402


class Unwrap(unittest.TestCase):
    def test_parameters_and_arguments_wrappers(self):
        self.assertEqual(unwrap_params({"parameters": '{"path": "/tmp/a", "start_line": 1}'}), {"path": "/tmp/a", "start_line": 1})
        self.assertEqual(unwrap_params({"arguments": {"path": "/tmp/a"}}), {"path": "/tmp/a"})
        self.assertEqual(unwrap_params({"arguments": '{"path": "/tmp/a"}'}), {"path": "/tmp/a"})

    def test_anything_else_is_left_alone(self):
        for p in ({"path": "/tmp/a"}, {"parameters": "not json"}, {"arguments": '{"path": "/tmp/a'},
                  {"parameters": "[1]"}, {"parameters": 3}, {"arguments": "x", "path": "/tmp/a"}, {}):
            self.assertEqual(unwrap_params(p), p)


class Exec(unittest.TestCase):
    def test_the_last_bytes_before_the_exit_are_kept(self):
        t = LlamaTools(["exec_shell_command"])
        for i in range(30):
            got = t.call("exec_shell_command", {"command": f"sleep 0.0{i % 3}; printf 'tail{i}'"}, "/tmp")
            self.assertIn(f"tail{i}", got["plain_text_response"])
            self.assertIn("[exit code: 0]", got["plain_text_response"])


if __name__ == "__main__":
    unittest.main()


# 2026-11-08: web_search / fetch_url, offline (no network in the tests)
def test_parse_ddg_results_and_redirect():
    from serve.llama_tools import parse_ddg
    page = ('<div class="result results_links"><a rel="nofollow" class="result__a" '
            'href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa%3Fb%3D1&amp;rut=x">An <b>Example</b></a>'
            '<a class="result__snippet" href="#">Some &amp; text</a></div>'
            '<div class="result result--ad"><a class="result__a" href="//duckduckgo.com/y.js?ad=1">Ad</a></div>')
    assert parse_ddg(page) == [{"title": "An Example", "url": "https://example.com/a?b=1", "snippet": "Some & text"}]


def test_html_text_drops_scripts_and_keeps_blocks():
    from serve.llama_tools import html_text
    title, text = html_text("<html><head><title>T  1</title><style>x{}</style></head><body><nav>menu</nav>"
                            "<p>Hello <b>world</b></p><script>bad()</script><ul><li>a</li><li>b</li></ul></body></html>")
    assert title == "T 1"
    assert "bad" not in text and "menu" not in text and "x{}" not in text
    assert text.splitlines()[0] == "Hello world" and "- a" in text and "- b" in text


def test_fetch_url_only_http():
    from serve.llama_tools import LlamaTools
    r = LlamaTools(["all"]).call("fetch_url", {"url": "file:///etc/passwd"})
    assert "error" in r and "http" in r["error"]


def test_web_tools_listed():
    from serve.llama_tools import LlamaTools
    names = [x["tool"] for x in LlamaTools(["all"]).listing()]
    assert "web_search" in names and "fetch_url" in names
