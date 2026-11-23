import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from polisher.providers import ProviderError, make_provider


@pytest.fixture
def server():
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.update(path=self.path, headers=dict(self.headers), body=body)
            if self.path == "/v1/messages":
                reply = {"content": [{"type": "text", "text": "anthropic-ok"}]}
            elif self.path.endswith("/chat/completions"):
                reply = {"choices": [{"message": {"content": "openai-ok"}}]}
            elif self.path == "/api/chat":
                reply = {"message": {"content": "ollama-ok"}}
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"nope")
                return
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", seen
    httpd.shutdown()


def call(provider):
    return provider.complete("SYS", "USER", temperature=0.2, max_tokens=100)


def test_anthropic_shape(server):
    url, seen = server
    p = make_provider("anthropic", {"model": "m", "base_url": url, "api_key": "k"})
    assert call(p) == "anthropic-ok"
    assert seen["headers"]["x-api-key"] == "k"
    assert seen["body"]["system"] == "SYS" and seen["body"]["messages"][0]["content"] == "USER"
    assert seen["body"]["max_tokens"] == 100


def test_openai_compatible_shape_and_optional_key(server):
    url, seen = server
    p = make_provider("lmstudio", {"kind": "openai", "model": "m", "base_url": url + "/v1"})
    assert call(p) == "openai-ok"  # local servers need no key
    assert "Authorization" not in seen["headers"]
    assert seen["body"]["messages"][0] == {"role": "system", "content": "SYS"}


def test_ollama_shape(server):
    url, seen = server
    p = make_provider("ollama", {"model": "m", "base_url": url})
    assert call(p) == "ollama-ok"
    assert seen["body"]["stream"] is False and seen["body"]["options"]["num_predict"] == 100


def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("NOPE_KEY", raising=False)
    p = make_provider("anthropic", {"model": "m", "api_key_env": "NOPE_KEY"})
    with pytest.raises(ProviderError, match="NOPE_KEY"):
        call(p)


def test_http_error_and_unreachable(server):
    url, _ = server
    bad = make_provider("anthropic", {"model": "m", "base_url": url + "/wrong", "api_key": "k"})
    with pytest.raises(ProviderError, match="404"):
        call(bad)
    down = make_provider("ollama", {"model": "m", "base_url": "http://127.0.0.1:9"})
    with pytest.raises(ProviderError, match="Cannot reach"):
        call(down)


def test_unknown_provider():
    with pytest.raises(ProviderError):
        make_provider("mystery", {})
