#!/usr/bin/env bash
# Root prologue before dropping to the unprivileged 'worker' user.
#
# Guest-kernel hardening that a non-root process can't do. Fly Machines are
# x86 Firecracker microVMs with NO ACPI/power-management: a guest kernel that
# panics with kernel.panic=0 (the default) spins forever — network, log stream
# and metrics scrape all dead while flyd still reports the machine "started".
# That is indistinguishable from the 2026-07-13/14 freeze incidents, so:
#
#   kernel.panic=10           a panicked guest reboots after 10 s instead of
#                             freezing eternally (reboot is the ONE exit that
#                             works in Firecracker; poweroff/sysrq-o just spin)
#   kernel.softlockup_panic=1 turn silent CPU lockups into that panic-reboot
#
# If the mystery freezes are guest panics/lockups, machines will now visibly
# self-reboot where they used to freeze — a mitigation that doubles as the
# diagnostic.
#
# Manual hard-exit from inside (fly ssh console, root): `busybox reboot -f`
# or `echo b > /proc/sysrq-trigger`. Do NOT use poweroff/halt/sysrq-o — they
# dead-spin the VM (no pm_power_off on x86 Firecracker).

# echo-to-/proc rather than the sysctl binary: no dependencies at boot time.
echo 10 > /proc/sys/kernel/panic 2>/dev/null \
	&& echo "entrypoint: kernel.panic=10 (panic -> reboot instead of eternal freeze)" \
	|| echo "entrypoint: FAILED to set kernel.panic (continuing)"
echo 1 > /proc/sys/kernel/softlockup_panic 2>/dev/null \
	&& echo "entrypoint: kernel.softlockup_panic=1" \
	|| echo "entrypoint: could not set kernel.softlockup_panic (continuing)"

# setpriv changes uid/gid but NOT the environment: without this the dropped
# process keeps HOME=/root and e.g. ultralytics fails writing ~/.config at
# import. (Not --reset-env — that would wipe the app's whole [env] config.)
export HOME=/home/worker USER=worker LOGNAME=worker
exec setpriv --reuid=worker --regid=worker --init-groups /app/worker/start.sh
