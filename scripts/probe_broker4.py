"""
Probe with the correct XWB NS-mode packet format derived from XWBPRS.m source.

Protocol analysis:
  CONNTYPE reads 5 bytes: [XWB]
  PRSP     reads 4 bytes: ver(1) type(1) lenv(1) rt(1) — each a single ASCII digit
  PRSM     reads chunks:
    "1" → PRS1: SREAD(version) + SREAD(return_type)
    "2" → PRS2: SREAD(rpc_ver) + SREAD(rpc_name)
    "4" → PRS4: SREAD(command)          — exits if cmd not in "TCPConnect^#BYE#"
    "5" → PRS5: repeated TY+LREAD+CONT until TY=\x04 (EOT)

SREAD: 1 byte length ($A), then that many bytes.
LREAD: lenv bytes as decimal (lenv=3 → "009"), then that many bytes.

For TCPConnect (connect packet):
  chunks 4 then 5
  chunk4 command = "TCPConnect"
  chunk5 params  = IP, port, app, UCI  (each literal: \x00 + "009..." + "f")
  terminated by \x04 as next TY inside PRS5

Run inside the container:
    python3 /opt/vista-fm-browser/scripts/probe_broker4.py
"""

import socket
import time


def sread(s: str) -> bytes:
    """Single-byte length prefix (for SREAD in M)."""
    b = s.encode("latin-1")
    assert len(b) < 256, f"sread value too long: {s!r}"
    return bytes([len(b)]) + b


def lread(s: str, lenv: int = 3) -> bytes:
    """Decimal length prefix padded to lenv chars (for LREAD in M)."""
    b = s.encode("latin-1")
    prefix = f"{len(b):0{lenv}d}".encode()
    return prefix + b


def build_connect(
    app: str, uci: str, ip: str = "127.0.0.1", port: str = "9430"
) -> bytes:
    """Build a TCPConnect packet that XWBPRS.m will accept."""
    return (
        b"[XWB]"  # CONNTYPE reads 5 bytes
        b"1030"  # PRSP: ver=1, type=0, lenv=3, rt=0
        b"4"  # chunk 4 → PRS4
        + sread("TCPConnect")  # command string (1-byte len + value)
        + b"5"  # chunk 5 → PRS5
        # literal params: TY=\x00, LREAD(value), CONT="f"
        + b"\x00"
        + lread(ip)
        + b"f"
        + b"\x00"
        + lread(port)
        + b"f"
        + b"\x00"
        + lread(app)
        + b"f"
        + b"\x00"
        + lread(uci)
        + b"f"
        + b"\x04"  # TY=EOT → PRS5 done
    )


def build_rpc(rpc_name: str, params: list[str] = None) -> bytes:
    """Build an RPC call packet."""
    params = params or []
    chunk1 = b"1" + sread("") + sread("")  # header: empty ver + empty return
    chunk2 = b"2" + sread("0") + sread(rpc_name)  # rpc: ver + name
    if not params:
        chunk5 = b"5\x04"  # no params, immediate EOT
    else:
        param_bytes = b""
        for p in params:
            param_bytes += b"\x00" + lread(p) + b"f"
        param_bytes += b"\x04"
        chunk5 = b"5" + param_bytes
    return b"[XWB]1030" + chunk1 + chunk2 + chunk5


def raw_recv(s: socket.socket, timeout: float = 5.0) -> bytes:
    s.settimeout(timeout)
    data = b""
    try:
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
            if data.endswith(b"\x04"):
                break
    except (socket.timeout, ConnectionResetError):
        pass
    return data


HOST = "localhost"
PORT = 9430
APP = "FM BROWSER"
UCI = "VAH"

print("=== Corrected XWB NS-mode probe ===\n")

connect_pkt = build_connect(APP, UCI)
print(f"Connect packet ({len(connect_pkt)} bytes):")
print(f"  {connect_pkt!r}\n")

try:
    s = socket.create_connection((HOST, PORT), timeout=10)

    # Step 1: Connect
    s.sendall(connect_pkt)
    time.sleep(0.5)
    r1 = raw_recv(s, timeout=5.0)
    print(f"Connect response: {r1!r}")
    text = r1.decode("latin-1", errors="replace")
    print(f"Connect text:     {text!r}")

    if b"accept" in r1.lower() or (r1 and b"Job" not in r1):
        # Step 2: XUS SIGNON SETUP
        rpc1 = build_rpc("XUS SIGNON SETUP")
        print(f"\nXUS SIGNON SETUP pkt: {rpc1!r}")
        s.sendall(rpc1)
        time.sleep(0.5)
        r2 = raw_recv(s, timeout=5.0)
        print(f"SIGNON SETUP response: {r2[:200]!r}")

        if r2 and b"Job" not in r2:
            # Step 3: XUS AV CODE
            rpc2 = build_rpc("XUS AV CODE", ["fakedoc1;1Doc!@#$"])
            print(f"\nXUS AV CODE pkt: {rpc2!r}")
            s.sendall(rpc2)
            time.sleep(0.5)
            r3 = raw_recv(s, timeout=5.0)
            print(f"AV CODE response: {r3!r}")
    else:
        print("\nConnect not accepted — need to investigate further")

    s.close()
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

print("\nDone.")
