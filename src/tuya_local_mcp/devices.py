"""Construction of tinytuya connections and normalisation of their replies."""

from __future__ import annotations

from typing import Any

import tinytuya

from .discovery import passive_scan
from .registry import DeviceRecord


class DeviceError(RuntimeError):
    """A device was unreachable, rejected the key, or returned an error frame."""


# tinytuya reports failures as a dict with an "Error" key rather than raising.
def check(reply: Any, record: DeviceRecord) -> dict[str, Any]:
    if not isinstance(reply, dict):
        raise DeviceError(f"{record.name}: unexpected reply {reply!r}")

    if "Error" in reply:
        code = reply.get("Err")
        detail = reply.get("Error")
        hint = ""
        if code == "901":
            hint = " (network error - check the IP is current)"
        elif code == "914":
            hint = " (device rejected the local key; re-run the tinytuya wizard, "
            hint += "keys rotate when a device is re-paired)"
        elif code == "905":
            hint = " (device did not respond; it may be offline or busy with another connection)"
        raise DeviceError(f"{record.name}: {detail}{hint}")

    return reply


def locate(record: DeviceRecord, timeout: float) -> str:
    """Return the device's IP, falling back to a passive scan if unknown."""
    if record.ip:
        return record.ip

    for entry in passive_scan(timeout=timeout):
        if entry.get("device_id") == record.device_id:
            return entry["ip"]

    raise DeviceError(
        f"{record.name}: no IP in the device file and it did not broadcast within "
        f"{timeout:.0f}s. Re-run `python -m tinytuya scan` to refresh addresses."
    )


def connect(record: DeviceRecord, *, timeout: float, force_bulb: bool = False):
    """Build a tinytuya device object bound to `record`.

    Connections are non-persistent: each call opens and closes a socket. Many
    Tuya devices accept only one connection at a time, so holding one open
    would lock out the Smart Life app.
    """
    ip = locate(record, timeout=timeout)
    cls = tinytuya.BulbDevice if (force_bulb or record.is_light) else tinytuya.OutletDevice

    device = cls(record.device_id, address=ip, local_key=record.local_key)
    device.set_version(record.version_float)
    device.set_socketTimeout(timeout)
    device.set_socketPersistent(False)
    return device


def require_light(record: DeviceRecord) -> None:
    if not record.is_light:
        raise DeviceError(
            f"{record.name} is category {record.category!r}, which is not a light. "
            "Use set_datapoint if you know the datapoint number."
        )


def summarise(record: DeviceRecord, status: dict[str, Any]) -> dict[str, Any]:
    """Attach a human-readable reading of the datapoints where we can infer one.

    Tuya datapoint numbering is per-product. Bulbs use either the 1-5 range
    (older "A" series) or the 20-24 range ("B" series); switches and plugs
    almost always put the primary relay on datapoint 1.
    """
    dps = status.get("dps", {}) or {}
    reading: dict[str, Any] = {}

    for dp in ("1", "20"):
        if dp in dps and isinstance(dps[dp], bool):
            reading["on"] = dps[dp]
            reading["switch_dp"] = int(dp)
            break

    for dp, label, scale in (("3", "brightness_pct", 255), ("22", "brightness_pct", 1000)):
        if dp in dps and isinstance(dps[dp], int):
            reading[label] = round(dps[dp] / scale * 100)
            break

    for dp in ("2", "21"):
        if dp in dps and isinstance(dps[dp], str):
            reading["mode"] = dps[dp]
            break

    return {"device": record.public(), "dps": dps, "reading": reading}
