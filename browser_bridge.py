"""
========================================================================================
🌐 BROWSER INTEGRATION BRIDGE (IPC LOOPBACK SERVER) — Turbo Download Manager Pro
========================================================================================
High-performance, lightweight loopback IPC HTTP server for browser extension integration:
1. Listens strictly on 127.0.0.1 (default port 9242).
2. Supports Chrome, Edge, Brave, and Firefox WebExtensions.
3. Implements CORS preflight (OPTIONS) and JSON payload endpoints.
4. Thread-safe dispatch of intercepted URLs, filenames, and referrers to the GUI engine.
5. Standard library only: zero external dependencies.
========================================================================================
"""

import json
import logging
import socket
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Callable, Optional, Dict, Any
from urllib.parse import urlparse

DEFAULT_BRIDGE_HOST = "127.0.0.1"
DEFAULT_BRIDGE_PORT = 9242


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Threaded HTTP server to handle concurrent extension requests without blocking."""
    daemon_threads = True
    allow_reuse_address = True


class BrowserBridgeHandler(BaseHTTPRequestHandler):
    """
    HTTP Request Handler for browser extension communication:
    - GET /ping or /status: Connection health check
    - POST /download: Queue a new download task
    - OPTIONS *: CORS preflight response
    """

    # Suppress default server log output in console
    def log_message(self, format, *args):
        pass

    def _send_cors_headers(self, content_type: str = "application/json"):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Content-Type", content_type)
        self.send_header("Connection", "close")
        self.close_connection = True

    def do_OPTIONS(self):
        """Handle CORS preflight requests from browser extensions."""
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        """Handle health check and status probes."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path in ("/ping", "/status", ""):
            payload = {
                "status": "ok",
                "app": "Turbo Download Manager Pro",
                "version": "1.0.0",
                "active": True
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except Exception:
                pass
        elif path in ("/show", "/wake", "/restore"):
            server = getattr(self.server, "bridge_server_instance", None)
            if server and getattr(server, "on_show", None):
                try:
                    server.on_show()
                except Exception as e:
                    server.log(f"[BROWSER BRIDGE] Error in on_show callback: {e}")
            payload = {
                "status": "ok",
                "app": "Turbo Download Manager Pro",
                "message": "Window restored"
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except Exception:
                pass
        else:
            self._send_json_error(404, f"Endpoint '{self.path}' not found")

    def do_POST(self):
        """Handle incoming download interception or window restore from browser extension or second instance."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path in ("/show", "/wake", "/restore"):
            try:
                cl = int(self.headers.get("Content-Length", 0))
                if cl > 0:
                    self.rfile.read(cl)
            except Exception:
                pass
            server = getattr(self.server, "bridge_server_instance", None)
            if server and getattr(server, "on_show", None):
                try:
                    server.on_show()
                except Exception as e:
                    server.log(f"[BROWSER BRIDGE] Error in on_show callback: {e}")
            payload = {
                "success": True,
                "app": "Turbo Download Manager Pro",
                "message": "Window restored"
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except Exception:
                pass
            return

        if path != "/download":
            self._send_json_error(404, f"Unknown POST endpoint '{self.path}'")
            return

        # Read content length
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            self._send_json_error(400, "Invalid Content-Length header")
            return

        if content_length <= 0:
            self._send_json_error(400, "Empty request body")
            return

        if content_length > 1024 * 1024:  # 1MB limit for JSON payload
            self._send_json_error(413, "Request body exceeds maximum size (1MB)")
            return

        try:
            raw_body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(raw_body)
        except Exception as e:
            self._send_json_error(400, f"Malformed JSON: {e}")
            return

        if not isinstance(data, dict):
            self._send_json_error(400, "JSON payload must be an object")
            return

        raw_url = data.get("url")
        if not raw_url or not isinstance(raw_url, str) or not raw_url.strip():
            self._send_json_error(400, "Field 'url' is required and must be a non-empty string")
            return

        url = raw_url.strip()

        # Validate basic URL scheme
        url_lower = url.lower()
        if not (url_lower.startswith("http://") or url_lower.startswith("https://") or url_lower.startswith("ftp://")):
            self._send_json_error(400, "URL must have http, https, or ftp scheme")
            return

        filename = data.get("filename", "")
        referrer = data.get("referrer", "")
        headers = data.get("headers", {})
        start_immediately = bool(data.get("start_immediately", True))

        # Forward task to registered application callback
        server: BrowserBridgeServer = self.server.bridge_server_instance  # type: ignore
        if server and server.on_download:
            try:
                server.on_download({
                    "url": url,
                    "filename": str(filename).strip(),
                    "referrer": str(referrer).strip(),
                    "headers": dict(headers) if isinstance(headers, dict) else {},
                    "start_immediately": start_immediately
                })
            except Exception as e:
                self._send_json_error(500, f"Error processing download callback: {e}")
                return

        response_payload = {
            "success": True,
            "message": "Download task received and dispatched to Turbo Download Manager Pro",
            "url": url
        }
        body = json.dumps(response_payload).encode("utf-8")
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json_error(self, code: int, message: str):
        payload = {
            "success": False,
            "error": message,
            "code": code
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self._send_cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass


class BrowserBridgeServer:
    """
    Manages the lifecycle of the local IPC loopback HTTP server.
    """

    def __init__(
        self,
        host: str = DEFAULT_BRIDGE_HOST,
        port: int = DEFAULT_BRIDGE_PORT,
        on_download: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
        on_show: Optional[Callable[[], None]] = None
    ):
        self.host = host
        self.port = port
        self.on_download = on_download
        self.on_log = on_log
        self.on_show = on_show

        self.httpd: Optional[ThreadedHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._is_running = False

    def log(self, msg: str):
        if self.on_log:
            try:
                self.on_log(msg)
            except Exception:
                pass

    def start(self) -> bool:
        """
        Starts the loopback HTTP listener in a background daemon thread.
        Returns True if successfully started, False if already running or failed.
        """
        with self._lock:
            if self._is_running:
                return True

            try:
                self.httpd = ThreadedHTTPServer((self.host, self.port), BrowserBridgeHandler)
                # Attach reference to self on the server instance
                setattr(self.httpd, "bridge_server_instance", self)
                self._is_running = True
            except OSError as e:
                self.log(f"[BROWSER BRIDGE ERROR] Failed to bind to {self.host}:{self.port}: {e}")
                self._is_running = False
                return False

            self._thread = threading.Thread(target=self._serve, daemon=True, name="BrowserBridgeListener")
            self._thread.start()

        self.log(f"[BROWSER BRIDGE] Loopback IPC server active on http://{self.host}:{self.port}")
        return True

    def _serve(self):
        try:
            if self.httpd:
                self.httpd.serve_forever(poll_interval=0.5)
        except Exception as e:
            self.log(f"[BROWSER BRIDGE] Server error: {e}")
        finally:
            self._is_running = False

    def stop(self):
        """Stops the loopback server cleanly."""
        with self._lock:
            if not self._is_running:
                return

            self._is_running = False
            if self.httpd:
                try:
                    self.httpd.shutdown()
                    self.httpd.server_close()
                except Exception:
                    pass
                self.httpd = None

        self.log("[BROWSER BRIDGE] Loopback IPC server stopped.")

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running
