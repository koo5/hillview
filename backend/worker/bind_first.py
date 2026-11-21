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

Dual-stack: this is the DEV_MODE / aux path (watchmedo -> start2.sh -> here;
boot.py's early bind is skipped under DEV_MODE), and the aux worker runs
network_mode: host on a box with a public IPv6 address, so it binds ONE
AF_INET6 socket on [::] with IPV6_V6ONLY=0 — IPv4 peers arrive on the same
socket as v4-mapped ::ffff:a.b.c.d (nothing in the worker inspects client
addresses). Where the kernel has no IPv6 it falls back to 0.0.0.0. boot.py
(prod, Fly) deliberately still binds plain 0.0.0.0: fly-proxy reaches the
machine over private IPv4, and the .fly.dev edge already terminates IPv6.
"""
import errno
import os
import socket

port = int(os.environ.get("WORKER_PORT", "8056"))
sock = None
if socket.has_dualstack_ipv6():
	try:
		sock = socket.create_server(("::", port), family=socket.AF_INET6, dualstack_ipv6=True, backlog=128)
	except OSError as e:
		if e.errno == errno.EADDRINUSE:
			raise
		print(f"bind_first: dual-stack bind failed ({e}) — falling back to IPv4-only", flush=True)
if sock is None:
	sock = socket.create_server(("0.0.0.0", port), backlog=128)
bound = f"[::]:{port} dual-stack (v4+v6)" if sock.family == socket.AF_INET6 else f"0.0.0.0:{port}"
sock.set_inheritable(True)
print(f"bind_first: {bound} listening (fd={sock.fileno()}), exec'ing uvicorn", flush=True)
os.execvp("uvicorn", ["uvicorn", "app:app", "--fd", str(sock.fileno()), "--loop", "uvloop"])
