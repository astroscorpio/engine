"""Single-threaded local server for the compute API, for development.

Single-threaded on purpose: Swiss Ephemeris keeps the sidereal mode in
process-global state, so two requests must never interleave.

    python devserver.py [port]      # default 8790
"""

from __future__ import annotations

import logging
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit

from astro_compute.app import dumps, handle, query_dict


class Handler(BaseHTTPRequestHandler):
    def _serve(self, method: str) -> None:
        url = urlsplit(self.path)
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k.lower(): v for k, v in self.headers.items()}
        status, payload = handle(method, url.path, query_dict(url.query), body, headers)
        data = dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        self._serve("GET")

    def do_POST(self) -> None:
        self._serve("POST")

    def log_message(self, fmt: str, *args) -> None:
        logging.info("%s %s", self.address_string(), fmt % args)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8790
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
