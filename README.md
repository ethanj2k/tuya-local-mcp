# tuya-local-mcp

An [MCP](https://modelcontextprotocol.io) server that controls Tuya / Smart Life smart home devices **over your local network**. Once set up, no request touches Tuya's cloud — commands go straight to the device on your LAN, so they keep working with the internet down and aren't subject to cloud API rate limits.

Built on [tinytuya](https://github.com/jasonacox/tinytuya).

## The one catch, up front

"Local control" still requires **one** trip through Tuya's cloud. Each device has a 16-character `local_key` that's provisioned during pairing and is never broadcast on the network — you can't sniff it, derive it, or guess it. You fetch it once from the Tuya IoT Platform, and after that everything is local, forever.

There is no way around this short of reflashing the hardware with ESPHome or Tasmota. If you'd rather avoid the developer-console setup entirely, use a cloud-based Tuya MCP server instead; this project won't save you that step.

## Install

Requires Python 3.10+.

```bash
git clone https://github.com/ethanj2k/tuya-local-mcp
cd tuya-local-mcp
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e .
```

## Setup

### 1. Check your devices are visible

Before touching any credentials, confirm the devices are actually reachable. This listens for the UDP beacons Tuya devices broadcast every few seconds and **sends nothing**:

```bash
python scripts/passive_scan.py 15
```

```
3 device(s):

  192.168.1.50    udp/6667  beacons=3   proto=3.3   id=bf0000000000000000aaaa
  192.168.1.51    udp/6667  beacons=2   proto=3.4   id=bf0000000000000000bbbb
  192.168.1.52    udp/6667  beacons=3   proto=3.3   id=bf0000000000000000cccc
```

No output? See [Troubleshooting discovery](#troubleshooting-discovery) — on Windows the usual cause is the firewall, not the devices.

### 2. Get your local keys

1. Create an account at [iot.tuya.com](https://iot.tuya.com).
2. **Cloud → Development → Create Cloud Project.** Pick the data centre matching your region and "Smart Home" as the industry.
3. In the project, **Devices → Link App Account** and scan the QR code with the Smart Life / Tuya Smart app. This imports the devices you already own.
4. Run the wizard and paste in the project's Access ID and Access Secret:

```bash
python -m tinytuya wizard
```

This writes `devices.json` (your devices, with keys) and `snapshot.json` (the same, plus current IPs). **Both contain secrets — never commit them.** This repo's `.gitignore` already excludes them.

### 3. Point the server at the file

The server looks for `snapshot.json` then `devices.json` in the current directory, your home directory, and `~/.tinytuya/`. Override with `TUYA_DEVICES_FILE`.

### 4. Wire it into your MCP client

```json
{
  "mcpServers": {
    "tuya-local": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "tuya_local_mcp"],
      "env": {
        "TUYA_DEVICES_FILE": "/absolute/path/to/devices.json"
      }
    }
  }
}
```

On Windows the command is `C:\\path\\to\\.venv\\Scripts\\python.exe`.

## Tools

| Tool | Writes? | Description |
|---|---|---|
| `list_devices` | no | Every device in the registry — names, ids, IPs, protocol versions. Local keys are never returned. |
| `discover_devices` | no | Passively listen for devices broadcasting on the LAN. Flags any not in your registry. |
| `get_status` | no | Read one device's datapoints, plus a decoded reading of the common ones. |
| `get_all_status` | no | Read every device; per-device errors don't fail the whole call. |
| `set_power` | yes | Turn a device on or off. |
| `set_brightness` | yes | Set a light's brightness, 0–100%. |
| `set_color` | yes | Set a light's colour from hex (`#FF8800` or `f80`). |
| `set_color_temp` | yes | White mode at a colour temperature, 0 (warm) to 100 (cool). |
| `set_datapoint` | yes | Write a raw datapoint — the escape hatch for fans, curtains, valves, heaters. |

Devices are addressed by friendly name, device id, or IP. Name matching is case-insensitive and accepts unique substrings, so `"desk"` finds `"Desk Plug"`. Ambiguous matches raise an error listing the candidates rather than picking one.

## Read-only mode

Set `TUYA_READ_ONLY=1` and every write tool refuses. Discovery and status reads still work. Useful when you want an assistant that can answer "is the garage light on?" without being able to act, or while you're still building trust in a setup.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `TUYA_DEVICES_FILE` | auto-detected | Path to `devices.json` or `snapshot.json`. |
| `TUYA_READ_ONLY` | `0` | `1` blocks all state changes. |
| `TUYA_CONNECT_TIMEOUT` | `5` | Per-device socket timeout, seconds. |
| `TUYA_CACHE_TTL` | `10` | Seconds to cache status reads. `0` disables. |
| `TUYA_DISCOVERY_TIMEOUT` | `12` | Default listen window for `discover_devices`. |

## Troubleshooting discovery

If `passive_scan.py` hears nothing, work down this list before concluding the devices are offline.

**Windows: firewall rules are per-executable.** This one is easy to lose an hour to. Windows Firewall allows inbound traffic per *program path*, so if you previously allowed `C:\...\Python310\python.exe`, a virtualenv's `.venv\Scripts\python.exe` is a completely different program and its inbound UDP is silently dropped — no prompt, no error, just an empty scan. The same script will find devices on one interpreter and nothing on the other.

Check which interpreters are allowed:

```powershell
Get-NetFirewallApplicationFilter | Where-Object { $_.Program -like '*python*' } |
  ForEach-Object { $_.Program }
```

Add a rule for the interpreter you're actually running (elevated PowerShell):

```powershell
New-NetFirewallRule -DisplayName "Tuya LAN discovery" -Direction Inbound `
  -Program "C:\path\to\.venv\Scripts\python.exe" `
  -Protocol UDP -LocalPort 6666,6667,7000 -Action Allow
```

Note this only affects *discovery*. Device control is outbound TCP on port 6668 and works fine without any inbound rule — so a blocked scan does not mean a broken install. If your registry already has current IPs, everything else works.

**Devices on another network segment.** Beacons are broadcast and do not cross subnets or VLANs. IoT devices parked on a guest network won't be visible from your main one.

**Another listener holds the ports.** Home Assistant, a second copy of this script, or tinytuya's own scanner will contend for UDP 6666/6667. `passive_scan` raises if it can't bind anything.

**Beacons are periodic.** A 5-second window can genuinely miss a device. Try 30 seconds before worrying.

## Notes and known limits

**Protocol 3.4 / 3.5** devices use a session-key handshake rather than the local key directly. tinytuya supports them, but they're less battle-tested than 3.3 — if exactly one device misbehaves, check its version first.

**Local keys rotate** whenever a device is removed and re-paired in the app. Symptom is error 914; fix is re-running the wizard.

**One connection at a time.** Most Tuya devices accept a single TCP connection, so this server opens and closes a socket per call rather than holding one open. If a call times out, check nothing else (Home Assistant, another script) is polling that device continuously.

**Datapoint numbering is per-product.** The bulb helpers cover the two common layouts (datapoints 1–5 on older bulbs, 20–24 on newer). For anything else, `get_status` shows the raw datapoints and `set_datapoint` writes them.

**Discovery is best-effort.** Beacons are periodic, so a short listen window may miss devices that are simply between broadcasts. Increase the timeout rather than concluding a device is offline.

## Development

```bash
pip install -e ".[dev]"
pytest
```

The test suite runs entirely offline — no device, no network, no credentials. It includes a guard test asserting that `passive_scan` never calls `send`, `sendto`, `sendall`, or `connect` on a socket.

## License

MIT
