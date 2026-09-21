#!/usr/bin/env python3
"""Non-interactive replacement for `python -m tinytuya wizard`.

The stock wizard prompts for everything, which makes it awkward to run from a
script, a container, or an agent. This reads the same inputs from the
environment (or a .env file), pulls the device list from Tuya Cloud once, and
merges in LAN addresses from a passive scan.

    TUYA_API_KEY        Access ID       from iot.tuya.com -> project -> Overview
    TUYA_API_SECRET     Access Secret   same place
    TUYA_API_REGION     one of: cn us us-e eu eu-w in
    TUYA_API_DEVICE_ID  any device's Virtual ID, from the Smart Life app

Usage:
    python scripts/fetch_keys.py [--out devices.json] [--no-scan] [--scan-seconds 20]

Credentials are never printed, and the summary omits local keys. The output
file does contain them - keep it out of version control.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REQUIRED = ("TUYA_API_KEY", "TUYA_API_SECRET", "TUYA_API_REGION", "TUYA_API_DEVICE_ID")
VALID_REGIONS = {"cn", "us", "us-e", "eu", "eu-w", "in"}


def load_dotenv(path: Path) -> None:
    """Minimal .env reader - avoids a dependency for four variables."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="devices.json", help="output path")
    parser.add_argument("--no-scan", action="store_true", help="skip the LAN scan for IPs")
    parser.add_argument("--scan-seconds", type=float, default=20.0)
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()

    load_dotenv(Path(args.env_file))

    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        print("missing required variable(s): " + ", ".join(missing), file=sys.stderr)
        print(f"\nSet them in {args.env_file} or the environment. See --help.", file=sys.stderr)
        return 2

    region = os.environ["TUYA_API_REGION"].strip().lower()
    if region not in VALID_REGIONS:
        print(f"TUYA_API_REGION must be one of {sorted(VALID_REGIONS)}, got {region!r}",
              file=sys.stderr)
        return 2

    import tinytuya

    print(f"querying Tuya Cloud (region {region})...")
    cloud = tinytuya.Cloud(
        apiRegion=region,
        apiKey=os.environ["TUYA_API_KEY"].strip(),
        apiSecret=os.environ["TUYA_API_SECRET"].strip(),
        apiDeviceID=os.environ["TUYA_API_DEVICE_ID"].strip(),
    )

    devices = cloud.getdevices()
    if isinstance(devices, dict) and devices.get("Error"):
        print(f"cloud error: {devices.get('Error')}", file=sys.stderr)
        payload = devices.get("Payload")
        if payload:
            print(f"payload: {payload}", file=sys.stderr)
        print(
            "\nCommon causes:\n"
            "  'sign invalid'      -> TUYA_API_REGION does not match the project's data centre\n"
            "  'no permissions'    -> authorize IoT Core + Smart Home Scene Linkage on the project\n"
            "  empty device list   -> the Smart Life account is not linked to the project yet",
            file=sys.stderr,
        )
        return 1

    if not devices:
        print("cloud returned no devices - is the app account linked?", file=sys.stderr)
        return 1

    keyed = [d for d in devices if d.get("key")]
    print(f"cloud returned {len(devices)} device(s), {len(keyed)} with a local key")

    if not args.no_scan:
        from tuya_local_mcp.discovery import passive_scan

        print(f"listening {args.scan_seconds:.0f}s for LAN addresses (transmitting nothing)...")
        found = {e["device_id"]: e for e in passive_scan(timeout=args.scan_seconds) if e.get("device_id")}
        matched = 0
        for device in devices:
            beacon = found.get(device.get("id"))
            if beacon:
                device["ip"] = beacon["ip"]
                if beacon.get("version"):
                    device["version"] = beacon["version"]
                matched += 1
        print(f"matched {matched} device(s) to a LAN address")

    out = Path(args.out)
    out.write_text(json.dumps(devices, indent=2), encoding="utf-8")
    print(f"\nwrote {out}  (contains local keys - do not commit)\n")

    for device in sorted(devices, key=lambda d: str(d.get("name", ""))):
        print(f"  {str(device.get('name'))[:28]:<28} {device.get('ip') or 'no ip':<15} "
              f"v{device.get('version') or '?':<4} key={'yes' if device.get('key') else 'NO'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
