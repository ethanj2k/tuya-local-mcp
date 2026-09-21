import json
from hashlib import md5

import pytest

from tuya_local_mcp import discovery

PAYLOAD = {
    "ip": "192.168.1.77",
    "gwId": "bf4444444444444444dddd",
    "productKey": "keyexampleexample",
    "version": "3.3",
}


def _frame(body: bytes) -> bytes:
    """Wrap a payload in the 20-byte header / 8-byte trailer Tuya uses."""
    return b"\x00\x00U\xaa" + b"\x00" * 16 + body + b"\x00" * 8


def test_decodes_plaintext_beacon_on_6666():
    frame = _frame(json.dumps(PAYLOAD).encode())
    assert discovery._decode_beacon(frame, 6666) == PAYLOAD


def test_decodes_encrypted_beacon_on_6667():
    from Crypto.Cipher import AES

    raw = json.dumps(PAYLOAD).encode()
    pad = 16 - (len(raw) % 16)
    padded = raw + bytes([pad]) * pad
    key = md5(b"yGAdlopoPVldABfn").digest()
    encrypted = AES.new(key, AES.MODE_ECB).encrypt(padded)

    assert discovery._decode_beacon(_frame(encrypted), 6667) == PAYLOAD


def test_partial_payload_falls_back_to_field_scraping():
    broken = b'{"gwId":"bf5555","productKey":"keyabc","version":"3.4"'  # truncated
    result = discovery._decode_beacon(_frame(broken), 6666)
    assert result == {"gwId": "bf5555", "productKey": "keyabc", "version": "3.4"}


def test_undecodable_beacon_returns_empty_rather_than_raising():
    assert discovery._decode_beacon(_frame(b"\xff\xfe\xfd"), 6666) == {}


def test_strip_padding_handles_pkcs7_and_nulls():
    assert discovery._strip_padding(b"abc" + bytes([3]) * 3) == b"abc"
    assert discovery._strip_padding(b"abc\x00\x00") == b"abc"
    assert discovery._strip_padding(b"") == b""


def test_passive_scan_sends_no_packets(monkeypatch):
    """The scan must never transmit - it only ever binds and receives."""
    import socket as socket_module

    forbidden = ("send", "sendto", "sendall", "connect")

    class GuardedSocket(socket_module.socket):
        def __getattribute__(self, name):
            if name in forbidden:
                raise AssertionError(f"passive_scan called socket.{name}()")
            return super().__getattribute__(name)

    monkeypatch.setattr(discovery.socket, "socket", GuardedSocket)
    result = discovery.passive_scan(timeout=0.2)
    assert isinstance(result, list)


def test_passive_scan_raises_when_no_port_can_bind(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise OSError("address in use")

    class Unbindable:
        def setsockopt(self, *_):
            pass

        bind = refuse

        def close(self):
            pass

    monkeypatch.setattr(discovery.socket, "socket", lambda *a, **k: Unbindable())
    with pytest.raises(RuntimeError, match="could not bind"):
        discovery.passive_scan(timeout=0.1)
