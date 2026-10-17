"""Temporary HTTP probe for checking the SLAC reverse proxy before the portal is installed.

Run it on the app VM where nginx will later listen, then call the public URL from outside.
It answers every path, so it shows exactly what the proxy forwards (requirements §12.1):

    GET  .../anything          echo: path, client address, all request headers
    GET  .../big?mb=20         download of N MB (default 20)
    GET  .../sleep?t=60        answer after t seconds (finds the proxy timeout)
    POST .../up                upload; answers with the number of bytes received

Every request is also logged to the terminal. Only Python's standard library is used
(works with the VM's system Python 3.9). Stop it with Ctrl+C; nothing is installed.

    sudo python3 proxy_probe.py            # port 80 (needs root)
    python3 proxy_probe.py --port 8080
"""

import argparse
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

CHUNK = 1024 * 1024


class Probe(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path.endswith("/big"):
            self._download(int(query.get("mb", ["20"])[0]))
        elif url.path.endswith("/sleep"):
            seconds = int(query.get("t", ["0"])[0])
            time.sleep(seconds)
            self._text(f"slept {seconds} s\n")
        else:
            self._text(self._echo())

    def do_POST(self) -> None:
        received = self._read_body()
        self._text(f"received {received} bytes\n{self._echo()}")

    do_PUT = do_POST

    def _echo(self) -> str:
        lines = [
            f"method      {self.command}",
            f"path        {self.path}",
            f"client      {self.client_address[0]}",
            "headers:",
        ]
        lines += [f"  {name}: {value}" for name, value in self.headers.items()]
        return "\n".join(lines) + "\n"

    def _read_body(self) -> int:
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            total = 0
            while True:
                size = int(self.rfile.readline().split(b";")[0], 16)
                if size == 0:
                    self.rfile.readline()
                    return total
                total += len(self.rfile.read(size))
                self.rfile.readline()
        remaining = int(self.headers.get("Content-Length", 0))
        total = 0
        while remaining:
            data = self.rfile.read(min(CHUNK, remaining))
            if not data:
                break
            total += len(data)
            remaining -= len(data)
        return total

    def _text(self, body: str) -> None:
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _download(self, megabytes: int) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(megabytes * CHUNK))
        self.end_headers()
        block = bytes(range(256)) * (CHUNK // 256)
        for _ in range(megabytes):
            self.wfile.write(block)

    def log_message(self, format: str, *args: object) -> None:
        forwarded = self.headers.get("X-Forwarded-For", "-") if self.headers else "-"
        sys.stdout.write(f"{self.client_address[0]}  xff={forwarded}  {format % args}\n")
        sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=80)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Probe)
    print(f"Probe listening on port {args.port}; Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
