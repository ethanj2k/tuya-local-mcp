#!/usr/bin/env python3
"""Standalone passive scan - prints every Tuya device broadcasting on the LAN.

Sends nothing to any device; it only listens for the beacons they already emit.
Run this before the tinytuya wizard to confirm devices are reachable, or after
a DHCP change to see which addresses moved.

    python scripts/passive_scan.py [seconds]
"""

from __future__ import annotations

import sys

from tuya_local_mcp.discovery import passive_scan


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 15.0
    print(f"listening {seconds:.0f}s (transmitting nothing)...\n")

    try:
        devices = passive_scan(timeout=seconds)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not devices:
        print(
            "no beacons heard.\n\n"
            f"  interpreter: {sys.executable}\n\n"
            "  On Windows, firewall rules are per-executable - if you allowed a\n"
            "  different python.exe (a system install rather than this venv),\n"
            "  inbound UDP is dropped silently. See Troubleshooting in the README.\n"
            "  Other causes: devices on another VLAN/guest network, another tool\n"
            "  holding the ports, or simply too short a listen window."
        )
        return 1

    print(f"{len(devices)} device(s):\n")
    for entry in devices:
        print(f"  {entry['ip']:<15} udp/{entry['port']:<5} "
              f"beacons={entry['beacons']:<3} proto={entry['version'] or '?':<5} "
              f"id={entry['device_id'] or '(encrypted)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
