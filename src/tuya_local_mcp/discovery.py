"""Passive LAN discovery of Tuya devices.

Tuya devices broadcast a UDP beacon every few seconds announcing their device
id, protocol version and product key. This module only ever *listens* - it
opens no connection to any device and transmits nothing. That makes discovery
safe to run at any time, including while the Smart Life app is in use.

Port 6666 carries plaintext beacons (older firmware), 6667 carries the same
payload encrypted with a static AES key compiled into every Tuya device, and
7000 is used by some newer gear.
"""

from __future__ import annotations

import json
import re
import select
import socket
import time
from hashlib import md5
from typing import Any, Callable

BEACON_PORTS = (6666, 6667, 7000)

# Static key present in all Tuya firmware; publicly documented, not a secret.
_UDP_KEY = md5(b"yGAdlopoPVldABfn").digest()

# Tuya frames are 0x000055AA <20 byte header> <payload> <8 byte trailer>.
_HEADER_LEN = 20
_TRAILER_LEN = 8


def _build_decryptor() -> Callable[[bytes], bytes] | None:
    """Return an AES-ECB decrypt function from whichever crypto lib is present."""
    try:
        from Crypto.Cipher import AES

        return lambda blob: AES.new(_UDP_KEY, AES.MODE_ECB).decrypt(blob)
    except ImportError:
        pass

    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        def decrypt(blob: bytes) -> bytes:
            dec = Cipher(algorithms.AES(_UDP_KEY), modes.ECB()).decryptor()
            return dec.update(blob) + dec.finalize()

        return decrypt
    except ImportError:
        return None


_DECRYPT = _build_decryptor()


def _strip_padding(data: bytes) -> bytes:
    if not data:
        return data
    pad = data[-1]
    if 1 <= pad <= 16 and data.endswith(bytes([pad]) * pad):
        return data[:-pad]
    return data.rstrip(b"\x00")


def _decode_beacon(raw: bytes, port: int) -> dict[str, Any]:
    body = raw[_HEADER_LEN:-_TRAILER_LEN] if len(raw) > _HEADER_LEN + _TRAILER_LEN else raw

    if port != 6666 and _DECRYPT is not None:
        aligned = body[: len(body) - (len(body) % 16)]
        if aligned:
            try:
                body = _strip_padding(_DECRYPT(aligned))
            except Exception:  # noqa: BLE001 - a malformed beacon must not kill the scan
                pass

    text = body.decode("utf-8", "replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fall back to scraping the fields we care about out of partial payloads.
        found: dict[str, Any] = {}
        for key in ("gwId", "productKey", "version"):
            match = re.search(rf'"{key}"\s*:\s*"([^"]+)"', text)
            if match:
                found[key] = match.group(1)
        return found


def passive_scan(timeout: float = 12.0) -> list[dict[str, Any]]:
    """Listen for beacons and return one entry per distinct device.

    Sends nothing. Returns whatever announced itself within `timeout` seconds,
    which on a quiet network may be fewer devices than actually exist - beacons
    are periodic, so a longer timeout finds more.
    """
    sockets: list[tuple[int, socket.socket]] = []
    bind_errors: list[str] = []

    for port in BEACON_PORTS:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", port))
            sock.setblocking(False)
            sockets.append((port, sock))
        except OSError as exc:
            bind_errors.append(f"udp/{port}: {exc}")
            sock.close()

    if not sockets:
        raise RuntimeError(
            "could not bind any Tuya discovery port ("
            + "; ".join(bind_errors)
            + "). Another Tuya tool may already be listening."
        )

    by_ip: dict[str, dict[str, Any]] = {}
    deadline = time.monotonic() + timeout

    try:
        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            ready, _, _ = select.select([s for _, s in sockets], [], [], min(1.0, remaining))
            for sock in ready:
                port = next(p for p, s in sockets if s is sock)
                try:
                    raw, addr = sock.recvfrom(4096)
                except OSError:
                    continue

                beacon = _decode_beacon(raw, port)
                ip = addr[0]
                entry = by_ip.setdefault(
                    ip, {"ip": ip, "port": port, "beacons": 0, "device_id": None,
                         "product_key": None, "version": None}
                )
                entry["beacons"] += 1
                if beacon.get("gwId"):
                    entry["device_id"] = beacon["gwId"]
                if beacon.get("productKey"):
                    entry["product_key"] = beacon["productKey"]
                if beacon.get("version"):
                    entry["version"] = beacon["version"]
    finally:
        for _, sock in sockets:
            sock.close()

    return sorted(by_ip.values(), key=lambda e: tuple(int(o) for o in e["ip"].split(".")))
