"""The warm embedder: the same vectors as loading the model, over localhost.

Needs fastembed; skipped without it. The embedder's state file goes to a temp
folder, so a real one running for your sessions is left alone.
"""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    import fastembed  # noqa: F401
    HAVE_FASTEMBED = True
except ImportError:
    HAVE_FASTEMBED = False


def client(state_dir):
    """rag/embedder.py loaded with its state file in state_dir."""
    os.environ["GRAPH_MEMORY_STATE"] = str(state_dir)
    sys.path.insert(0, str(ROOT / "rag"))
    import importlib

    import embedder
    return importlib.reload(embedder)  # STATE is read at import


class NotRunning(unittest.TestCase):

    def test_no_embedder_means_no_vectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = client(tmp)
            self.assertIsNone(e.embed(["anything"]))
            self.assertFalse(e.running())

    def test_no_index_means_no_start(self):
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["GRAPH_MEMORY_RAG_DB"] = str(Path(tmp) / "none.db")
            try:
                e = client(tmp)
                with mock.patch.object(e.subprocess, "Popen") as popen:
                    e.start()
                popen.assert_not_called()
            finally:
                del os.environ["GRAPH_MEMORY_RAG_DB"]


@unittest.skipUnless(HAVE_FASTEMBED, "needs fastembed: python -m pip install fastembed")
class Warm(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.e = client(cls.tmp.name)
        env = {**os.environ, "GRAPH_MEMORY_STATE": cls.tmp.name}
        cls.proc = subprocess.Popen([sys.executable, str(ROOT / "rag" / "embedder.py"), "--serve"],
                                    env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(240):  # the model loads before the embedder answers
            if cls.e.running():
                break
            time.sleep(0.25)

    @classmethod
    def tearDownClass(cls):
        cls.e._ask({"stop": True}, timeout=2.0)
        cls.proc.wait(timeout=30)
        cls.tmp.cleanup()

    def test_same_vectors_as_loading_the_model(self):
        from fastembed import TextEmbedding

        warm = self.e.embed(["who signs off refunds?"])[0]
        local = list(TextEmbedding().embed(["who signs off refunds?"]))[0]
        dot = sum(a * b for a, b in zip(warm, local))
        norm = (sum(a * a for a in warm) ** 0.5) * (sum(b * b for b in local) ** 0.5)
        self.assertEqual(len(warm), 384)
        self.assertGreater(dot / norm, 0.9999)

    def test_a_request_without_the_key_gets_nothing(self):
        import json
        import socket

        port = json.loads(self.e.STATE.read_text(encoding="utf-8"))["port"]
        with socket.create_connection(("127.0.0.1", port), timeout=2) as s:
            s.sendall(b'{"key": "wrong", "texts": ["x"]}\n')
            s.settimeout(2)
            self.assertEqual(s.recv(100), b"")  # closed without an answer
        self.assertTrue(self.e.running())  # and still serving the right key


if __name__ == "__main__":
    unittest.main()
