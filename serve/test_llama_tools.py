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
