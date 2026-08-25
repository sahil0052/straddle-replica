# Isolated demo MT5 VPS runtime

This image runs one portable MetaTrader 5 terminal under Wine, Xvfb, and a
loopback-only VNC endpoint. It is designed to coexist with unrelated VPS
containers without modifying or restarting them.

Production constraints:

- publish VNC only as `127.0.0.1:15905:5900`;
- use a dedicated `/opt/straddle-replica-demo` data directory;
- cap the container at 1.5 GB RAM, 0.75 CPU, and 256 processes;
- drop Linux capabilities and enable `no-new-privileges`;
- first boot with MT5 Algo Trading disabled and no EA attached;
- do not enable the VPS EA while another terminal is managing the same magic.
