#!/usr/bin/env python3
"""Watchdog for FORGOTTEN emulators — runs from a systemd user timer every
few minutes (hillview-emu-watchdog.timer) and acts on ANY local AVD
process, however it was started. emulator.sh already caps what it starts;
this exists because emulators keep getting launched around it (ad-hoc
systemd-run, IDE, a Claude session) and an idle headless emulator burns
600%+ CPU indefinitely.

Two teeth:
  1. CLAMP: an emulator in an unquota'd transient scope (run-*.scope)
     gets CPUQuota applied on the spot, so a rogue start costs at most
     EMU_QUOTA while it lives.
  2. STOP: no adb traffic for EMU_IDLE_SECS -> the emulator is shut down.

"In use" = any of: byte counters moving on the emulator's TCP sockets
(adb + console — every shell/logcat/install/test moves them), an adb
client process alive (logcat tails count), or a device-test/appium/wdio
process running. The counters come from the kernel's sock_diag netlink
API (INET_DIAG_INFO -> tcp_info.bytes_acked/received) — the source ss -i
prints — matched to the emulator by its own socket inodes, so no text
scraping and no port guessing.

Caveat, accepted: hand-clicking a WINDOWED emulator with zero adb traffic
for the whole idle window looks idle and gets stopped — usage on this box
is adb-driven, and a restart is two minutes.

State in /tmp (reboot resets it, which is correct — a fresh boot starts a
fresh idle clock).
"""

import os
import signal
import socket
import struct
import subprocess
import sys
import time

IDLE_SECS = int(os.environ.get("EMU_IDLE_SECS", "1800"))
TRAFFIC_FLOOR = int(os.environ.get("EMU_TRAFFIC_FLOOR", "65536"))
QUOTA = os.environ.get("EMU_QUOTA", "200%")
SDK = os.environ.get("ANDROID_HOME", os.path.expanduser("~/Android/Sdk"))
ADB = os.path.join(SDK, "platform-tools", "adb")
STATE = "/tmp/hillview-emu-watchdog.state"

TESTER_WORDS = ("connectedAndroid", "androidDeviceTest", "appium", "wdio")


# ---- /proc: processes -------------------------------------------------

def iter_procs():
    """(pid, comm, argv) for every live process; argv from the NUL-split
    cmdline, so command lines with spaces can't confuse anything."""
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) == os.getpid():
            continue
        pid = int(entry)
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                argv = [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
            with open(f"/proc/{pid}/comm") as f:
                comm = f.read().strip()
        except OSError:
            continue  # raced with exit
        if argv:
            yield pid, comm, argv


def scan_processes():
    qemu, testers, adb_clients = [], [], []
    for pid, comm, argv in iter_procs():
        joined = " ".join(argv)
        if "qemu-system" in argv[0] and "-avd" in argv:
            qemu.append(pid)
        elif comm == "adb" and "fork-server" not in argv:
            adb_clients.append(pid)  # a client (shell, logcat, ...), not the server
        elif any(w in joined for w in TESTER_WORDS):
            testers.append(pid)
    return sorted(qemu), testers, adb_clients


def socket_inodes(pid):
    inodes = set()
    try:
        for fd in os.listdir(f"/proc/{pid}/fd"):
            try:
                target = os.readlink(f"/proc/{pid}/fd/{fd}")
            except OSError:
                continue
            if target.startswith("socket:["):
                inodes.add(int(target[8:-1]))
    except OSError:
        pass
    return inodes


def scope_unit(pid):
    """The systemd unit owning the pid, from its cgroup path."""
    try:
        with open(f"/proc/{pid}/cgroup") as f:
            path = f.read().strip().rpartition(":")[2]
    except OSError:
        return None
    leaf = path.rpartition("/")[2]
    return leaf or None


# ---- sock_diag netlink: the emulator's TCP sockets --------------------

NETLINK_SOCK_DIAG = 4
SOCK_DIAG_BY_FAMILY = 20
NLM_F_REQUEST, NLM_F_DUMP = 0x1, 0x300
NLMSG_DONE, NLMSG_ERROR = 3, 2
INET_DIAG_INFO = 2
TCP_ESTABLISHED, TCP_LISTEN = 1, 10
DIAG_MSG_LEN = 72  # inet_diag_msg: 4 header bytes + 48 sockid + 5 u32


def diag_dump(family, states, want_info):
    """Yield (sport, inode, tcp_info_bytes|None) for every TCP socket of
    the family in the given state mask."""
    ext = (1 << (INET_DIAG_INFO - 1)) if want_info else 0
    req = struct.pack("BBBxI48x", family, socket.IPPROTO_TCP, ext, states)
    hdr = struct.pack("=IHHII", 16 + len(req), SOCK_DIAG_BY_FAMILY,
                      NLM_F_REQUEST | NLM_F_DUMP, 1, 0)
    with socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, NETLINK_SOCK_DIAG) as nl:
        nl.settimeout(3)
        nl.sendto(hdr + req, (0, 0))
        while True:
            try:
                buf = nl.recv(1 << 16)
            except socket.timeout:
                return
            off = 0
            while off + 16 <= len(buf):
                nlen, ntype = struct.unpack_from("=IH", buf, off)
                if nlen < 16 or off + nlen > len(buf):
                    return
                if ntype in (NLMSG_DONE, NLMSG_ERROR):
                    return
                msg = buf[off + 16:off + nlen]
                off += (nlen + 3) & ~3
                if len(msg) < DIAG_MSG_LEN:
                    continue
                sport = struct.unpack_from(">H", msg, 4)[0]  # sockid, big-endian
                inode = struct.unpack_from("=I", msg, DIAG_MSG_LEN - 4)[0]
                info = None
                aoff = DIAG_MSG_LEN
                while aoff + 4 <= len(msg):
                    alen, atype = struct.unpack_from("=HH", msg, aoff)
                    if alen < 4 or aoff + alen > len(msg):
                        break
                    if atype == INET_DIAG_INFO:
                        info = msg[aoff + 4:aoff + alen]
                    aoff += (alen + 3) & ~3
                yield sport, inode, info


def traffic_bytes(qemu_pids):
    """Sum of bytes_acked + bytes_received over the emulator's SERVICE
    connections: established sockets the qemu process owns (inode match
    against /proc/<pid>/fd — counts each localhost flow once) whose local
    port is one the emulator LISTENS on (console, adbd, gRPC). Both
    filters matter: inode alone also sweeps in the guest's own internet
    sockets — user-mode networking makes every in-guest connection a
    qemu-owned host socket, and an idle guest still syncs and phones home
    at MB/min (measured) — while the service ports carry only what hosts
    do TO the emulator. Near-still when unused: TCP keepalives carry no
    payload, and the adb servers' device-tracking trickle stays under the
    noise floor."""
    inodes = set()
    for pid in qemu_pids:
        inodes |= socket_inodes(pid)
    ports = set()
    for family in (socket.AF_INET, socket.AF_INET6):
        for sport, inode, _info in diag_dump(family, 1 << TCP_LISTEN, False):
            if inode in inodes:
                ports.add(sport)
    conns, total = 0, 0
    for family in (socket.AF_INET, socket.AF_INET6):
        for sport, inode, info in diag_dump(family, 1 << TCP_ESTABLISHED, True):
            if sport not in ports or inode not in inodes:
                continue
            if info is None or len(info) < 136:
                continue
            acked, received = struct.unpack_from("=QQ", info, 120)  # tcp_info
            total += acked + received
            conns += 1
    return conns, total


# ---- the two teeth ----------------------------------------------------

def clamp(qemu_pids):
    for pid in qemu_pids:
        unit = scope_unit(pid)
        if not (unit and unit.startswith("run-") and unit.endswith(".scope")):
            # A terminal's scope or the session itself holds more than the
            # emulator — clamping it would throttle innocents.
            continue
        show = subprocess.run(
            ["systemctl", "--user", "show", "-p", "CPUQuotaPerSecUSec", "--value", unit],
            capture_output=True, text=True)
        if show.returncode == 0 and show.stdout.strip() == "infinity":
            done = subprocess.run(
                ["systemctl", "--user", "set-property", unit, f"CPUQuota={QUOTA}"])
            if done.returncode == 0:
                print(f"clamped {unit} (pid {pid}) to CPUQuota={QUOTA}")


def stop(qemu_pids):
    for env_port in (None, "5038"):  # default server + the external-tunnel one
        env = dict(os.environ)
        if env_port:
            env["ANDROID_ADB_SERVER_PORT"] = env_port
        subprocess.run([ADB, "emu", "kill"], env=env,
                       capture_output=True, timeout=15)
    for _ in range(5):
        time.sleep(3)
        if not any(os.path.exists(f"/proc/{p}") for p in qemu_pids):
            print("stopped gracefully")
            return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in qemu_pids:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        time.sleep(3)
        if not any(os.path.exists(f"/proc/{p}") for p in qemu_pids):
            break
    print("stopped (signalled)")


def main():
    qemu, testers, adb_clients = scan_processes()
    if not qemu:
        try:
            os.unlink(STATE)
        except OSError:
            pass
        return 0

    clamp(qemu)
    conns, bytes_now = traffic_bytes(qemu)

    now = int(time.time())
    prev_pids, prev_bytes, last_active = "", None, now
    try:
        with open(STATE) as f:
            prev_pids, prev_raw, last = f.read().strip().split("|")
            prev_bytes = int(prev_raw)
            last_active = int(last)
    except (OSError, ValueError):
        pass

    pids_key = ",".join(map(str, qemu))
    # The floor is what separates use from the adb servers' idle
    # device-tracking trickle (measured low single-digit KB/min here);
    # anything a human or a test does dwarfs it.
    moved = prev_bytes is None or abs(bytes_now - prev_bytes) > TRAFFIC_FLOOR
    if pids_key != prev_pids or moved or testers or adb_clients:
        last_active = now
    with open(STATE, "w") as f:
        f.write(f"{pids_key}|{bytes_now}|{last_active}\n")

    idle = now - last_active
    if idle < IDLE_SECS:
        print(f"emulator pid(s) {pids_key}: conns={conns} "
              f"bytes={bytes_now} idle={idle}s (limit {IDLE_SECS}s)")
        return 0

    print(f"emulator pid(s) {pids_key} idle {idle}s >= {IDLE_SECS}s — stopping")
    stop(qemu)
    try:
        os.unlink(STATE)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
