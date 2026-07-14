"""Root boot shim: bind the service port FIRST, then harden, drop, exec.

Replaces entrypoint-root.sh + the bind step of bind_first.py with one process,
so the listen socket exists within interpreter startup (~50 ms) of fly init
handing over — before the sysctls, before the privilege drop, before any bash
layer. Health checks and proxy wake requests racing the boot then queue in the
accept backlog instead of getting connection-refused.

Order of operations (and why the order):
  1. bind :WORKER_PORT           — the whole point; do it before anything else
  2. guest-kernel panic sysctls  — needs root. Fly Machines are x86 Firecracker
     microVMs with NO ACPI/power-management: a guest kernel that panics with
     kernel.panic=0 (default) spins forever — network, log stream and metrics
     scrape all dead while flyd still reports the machine "started"
     (indistinguishable from the 2026-07-13/14 freeze incidents). panic=10
     turns that into a 10 s self-reboot. (softlockup_panic is probed too, but
     Fly's guest kernel lacks CONFIG_SOFTLOCKUP_DETECTOR as of 2026-07-14.)
  3. drop to the 'worker' user   — initgroups/setgid/setuid + HOME/USER/LOGNAME
     (a bare setuid would keep HOME=/root and e.g. ultralytics fails writing
     ~/.config at import)
  4. exec start.sh               — unchanged flow (DEV_MODE watchmedo or
     start2.sh); start2.sh sees WORKER_SOCKET_FD and gives uvicorn --fd the
     inherited socket. Under watchmedo the fd survives restarts, so dev
     reloads re-serve the same socket with no rebind gap.

Manual hard-exit from inside a machine (fly ssh console, root):
`busybox reboot -f` or `echo b > /proc/sysrq-trigger`. Do NOT use
poweroff/halt/sysrq-o — with no pm_power_off they dead-spin the VM.
"""
import os
import pwd
import socket

if os.environ.get("DEV_MODE"):
	# watchmedo (a Python program) spawns start2.sh with subprocess's default
	# close_fds=True — an early-bound fd would die at that hop while
	# WORKER_SOCKET_FD still points at it (uvicorn: "operation on non-socket"),
	# and the parent-held socket would EADDRINUSE the fallback bind. Dev
	# restarts just bind late via bind_first.py; early-bind is a prod-boot
	# optimization.
	print("boot: DEV_MODE — skipping early bind (bind_first.py binds per watchmedo restart)", flush=True)
else:
	port = int(os.environ.get("WORKER_PORT", "8056"))
	sock = socket.create_server(("0.0.0.0", port), backlog=128)
	sock.set_inheritable(True)
	os.environ["WORKER_SOCKET_FD"] = str(sock.fileno())
	print(f"boot: :{port} listening (fd={sock.fileno()})", flush=True)


def _sysctl(path, value):
	try:
		with open(path, "w") as f:
			f.write(value)
		print(f"boot: {path}={value}", flush=True)
	except OSError as e:
		print(f"boot: could not set {path} ({e}) — continuing", flush=True)


if os.getuid() == 0:
	_sysctl("/proc/sys/kernel/panic", "10")
	_sysctl("/proc/sys/kernel/softlockup_panic", "1")
	pw = pwd.getpwnam("worker")
	os.initgroups("worker", pw.pw_gid)
	os.setgid(pw.pw_gid)
	os.setuid(pw.pw_uid)
	os.environ.update(HOME=pw.pw_dir, USER="worker", LOGNAME="worker")
	print(f"boot: dropped to worker (uid={pw.pw_uid}), HOME={pw.pw_dir}", flush=True)
else:
	print(f"boot: not root (uid={os.getuid()}) — skipping sysctls and privilege drop", flush=True)

os.execv("/app/worker/start.sh", ["/app/worker/start.sh"])
