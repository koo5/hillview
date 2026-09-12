#!/usr/bin/env python3
"""A one-route proxy, so a rented GPU box never sees the workbench API.

WHY. The worker needs exactly one thing from the workbench: POST /api/recon/result. The
tunnel that gives it that would, if pointed at 8070, also give it queue purges, run
imports, every artifact and the photo mirror — on an API whose own config file says it is
unauthenticated by design, running on a machine rented by the hour from a stranger. The
photos are public and the queue is reconstructible, so the blast radius is bounded, but it
includes overwriting artifacts and fabricating the metrics the bench ranks runs by.

So: forward THIS instead of 8070. It accepts one method on one path, streams the body
through without buffering it (a dense run's callback is tens of megabytes and both ends
are memory-capped), and answers everything else with 404 — not 403, because a scanner
learns less from a door that is not there.

    python3 callback_proxy.py            # 127.0.0.1:8075 -> 127.0.0.1:8070
    RECON_PROXY_PORT=9000 UPSTREAM=127.0.0.1:8070 python3 callback_proxy.py

Then tunnel that port rather than the API's:

    ssh -N -R 8070:127.0.0.1:8075 root@<instance> -p <port>

The instance still believes it is talking to 8070 on its own loopback, which is what the
worker's defaults expect, and it is.
"""
import http.client
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALLOWED_PATH = os.getenv("RECON_PROXY_PATH", "/api/recon/result")
UPSTREAM = os.getenv("UPSTREAM", "127.0.0.1:8070")
PORT = int(os.getenv("RECON_PROXY_PORT", "8075"))
CHUNK = 1 << 16
# Generous: a 300-frame dense callback is tens of megabytes over a rented box's uplink.
TIMEOUT = float(os.getenv("RECON_PROXY_TIMEOUT", "600"))
# Refuse a body larger than any real callback, so a hostile client cannot stream forever.
MAX_BODY = int(os.getenv("RECON_PROXY_MAX_BODY", str(512 << 20)))


class OneRoute(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "recon-callback-proxy"
    sys_version = ""

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _closed_door(self):
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = do_HEAD = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = lambda self: self._closed_door()

    def do_POST(self):
        if self.path.split("?", 1)[0] != ALLOWED_PATH:
            return self._closed_door()
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._closed_door()
        if length <= 0 or length > MAX_BODY:
            return self._closed_door()

        host, _, port = UPSTREAM.partition(":")
        conn = http.client.HTTPConnection(host, int(port or 80), timeout=TIMEOUT)
        try:
            conn.putrequest("POST", self.path, skip_host=True, skip_accept_encoding=True)
            # only what the callback actually needs: its multipart framing and its token
            for h in ("Content-Type", "Content-Length", "X-Worker-Token"):
                v = self.headers.get(h)
                if v is not None:
                    conn.putheader(h, v)
            conn.putheader("Host", UPSTREAM)
            conn.endheaders()
            left = length
            while left > 0:
                buf = self.rfile.read(min(CHUNK, left))
                if not buf:
                    break
                conn.send(buf)
                left -= len(buf)
            resp = conn.getresponse()
            body = resp.read()
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.getheader("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:  # never leak an upstream detail to the rented box
            sys.stderr.write(f"proxy: upstream failed: {type(e).__name__}: {e}\n")
            self.send_response(502)
            self.send_header("Content-Length", "0")
            self.end_headers()
        finally:
            conn.close()


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), OneRoute)
    sys.stderr.write(f"recon-callback-proxy: 127.0.0.1:{PORT} -> {UPSTREAM}{ALLOWED_PATH} "
                     f"(everything else 404)\n")
    srv.serve_forever()
