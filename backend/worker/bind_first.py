"""Bind the service port immediately, then exec uvicorn on the inherited fd.

Socket-activation for the startup gap (the modern form of the inetd trick):
uvicorn takes seconds to import app.py before it binds, and during that window
TCP connects to :8056 are REFUSED — Fly health checks fail ("warn" until the
first pass) and a proxy waking this machine for a request burns its ~8-10 s
connect budget. This bootstrap is stdlib-only, so the port is LISTENING within
~0.1 s of process start: the kernel completes handshakes into the accept
backlog, early health checks and the wake request simply queue, and they get
answered as soon as uvicorn starts accepting (well inside the check's 25 s
timeout). uvicorn inherits the already-bound socket via --fd.
"""
import os
import socket

port = int(os.environ.get("WORKER_PORT", "8056"))
sock = socket.create_server(("0.0.0.0", port), backlog=128)
sock.set_inheritable(True)
print(f"bind_first: :{port} listening (fd={sock.fileno()}), exec'ing uvicorn", flush=True)
os.execvp("uvicorn", ["uvicorn", "app:app", "--fd", str(sock.fileno()), "--loop", "uvloop"])
