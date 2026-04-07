"""Sprout API 服务启动入口。"""

from __future__ import annotations

import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .http_api import SproutHttpApi


class _SproutApiHandler(BaseHTTPRequestHandler):
    """标准库 HTTP 处理器。"""

    api = SproutHttpApi()

    def do_GET(self) -> None:  # noqa: N802
        self._handle_request()

    def do_POST(self) -> None:  # noqa: N802
        self._handle_request()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _handle_request(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api_request()
            return
        self._handle_static_request()

    def _handle_api_request(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(content_length) if content_length > 0 else None
        status_code, headers, response_body = self.api.handle_request(
            method=self.command,
            raw_path=self.path,
            body=body,
        )
        self.send_response(status_code)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def _handle_static_request(self) -> None:
        try:
            file_path = self._resolve_static_file_path(self.path)
            mime_type, _ = mimetypes.guess_type(str(file_path))
            response_body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime_type or "application/octet-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)
        except FileNotFoundError as exc:
            status_code, headers, response_body = self.api._json_response(404, {"error": str(exc)})
            self.send_response(status_code)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

    @classmethod
    def _resolve_static_file_path(cls, raw_path: str) -> Path:
        web_root = Path(__file__).resolve().parents[1] / "web"
        parsed_url = urlsplit(raw_path)
        relative_path = unquote(parsed_url.path).lstrip("/")
        if not relative_path:
            relative_path = "pages/index.html"
        candidate_path = (web_root / relative_path).resolve()
        if not cls._is_relative_to(candidate_path, web_root.resolve()):
            raise FileNotFoundError("静态资源路径非法。")
        if candidate_path.is_dir():
            candidate_path = candidate_path / "index.html"
        if not candidate_path.exists():
            raise FileNotFoundError(f"静态资源不存在：{candidate_path}")
        return candidate_path

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False


def run_sprout_api_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    """启动 Sprout API 服务。"""

    server = ThreadingHTTPServer((host, port), _SproutApiHandler)
    print(f"Sprout API 已启动：http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Sprout API 已停止。")
    finally:
        server.server_close()
