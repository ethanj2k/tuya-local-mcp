#!/usr/bin/env python3
"""Summarise a devices.json without printing local keys.

Separates directly-addressable WiFi devices from Zigbee/BLE sub-devices, which
sit behind a gateway and cannot be reached by IP on their own.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "devices.json")
devices = json.loads(path.read_text(encoding="utf-8"))

subs, wifi = [], []
for d in devices:
    is_sub = bool(d.get("node_id")) or bool(d.get("gateway_id"))
    (subs if is_sub else wifi).append(d)

print(f"{path}: {len(devices)} device(s) - {len(wifi)} direct, {len(subs)} sub-device(s)\n")

print("DIRECT (reachable over LAN by IP)")
for d in sorted(wifi, key=lambda x: str(x.get("name", ""))):
    print(f"  {str(d.get('name'))[:26]:<26} {d.get('ip') or '-':<15} "
          f"v{str(d.get('version') or '?'):<4} cat={str(d.get('category') or '?'):<6} "
          f"id={str(d.get('id'))[:22]}")

if subs:
    print("\nSUB-DEVICES (behind a gateway; need parent routing)")
    for d in sorted(subs, key=lambda x: str(x.get("name", ""))):
        print(f"  {str(d.get('name'))[:26]:<26} parent={str(d.get('parent') or '?')[:22]:<22} "
              f"node={str(d.get('node_id') or '?')[:18]:<18} cat={d.get('category') or '?'}")

keys = {k for d in devices for k in d}
print(f"\nfields present across entries: {sorted(keys)}")
