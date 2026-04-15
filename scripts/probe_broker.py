"""
Raw broker probe — prints exactly what the VEHU broker sends at each step.
Run inside the container:
    python3 /opt/vista-fm-browser/scripts/probe_broker.py

Protocol notes (from XWBPRS.m source analysis — see probe_broker4.py):
  - Correct connect format: [XWB]1030 + chunk4(TCPConnect) + chunk5(ip,port,app,uci)
  - [XWB]10304\\nTCPCONNECT5\\n format (old NS) does NOT get a response from VEHU
  - Server responds with \\x00\\x00accept\\x04 on success
"""

import socket
import time

HOST = "localhost"
PORT = 9430


def sread(s: str) -> bytes:
    """Single-byte length prefix (SREAD in XWBPRS.m)."""
    b = s.encode("latin-1")
    assert len(b) < 256
    return bytes([len(b)]) + b


def lread(s: str, lenv: int = 3) -> bytes:
    """Decimal length prefix padded to lenv chars (LREAD in XWBPRS.m)."""
    b = s.encode("latin-1")
    return f"{len(b):0{lenv}d}".encode() + b


def build_connect(app: str, uci: str, ip: str = "127.0.0.1", port: str = "9430") -> bytes:
    """Build a TCPConnect packet that XWBPRS.m will accept."""
    return (
        b"[XWB]"              # CONNTYPE reads 5 bytes
        b"1030"               # PRSP: ver=1, type=0, lenv=3, rt=0
        b"4"                  # chunk 4 → PRS4
        + sread("TCPConnect") # command (1-byte len + value)
        + b"5"                # chunk 5 → PRS5
        + b"\x00" + lread(ip)   + b"f"
        + b"\x00" + lread(port) + b"f"
        + b"\x00" + lread(app)  + b"f"
        + b"\x00" + lread(uci)  + b"f"
        + b"\x04"             # EOT → PRS5 done
    )


def build_rpc(rpc_name: str, params: list[str] | None = None) -> bytes:
    """Build an RPC call packet."""
    params = params or []
    chunk1 = b"1" + sread("") + sread("")         # ver + return_type (empty)
    chunk2 = b"2" + sread("0") + sread(rpc_name)  # rpc_ver + rpc_name
    if not params:
        chunk5 = b"5\x04"
    else:
        param_bytes = b"".join(b"\x00" + lread(p) + b"f" for p in params)
        chunk5 = b"5" + param_bytes + b"\x04"
    return b"[XWB]1030" + chunk1 + chunk2 + chunk5


def recv_all(s: socket.socket, label: str) -> bytes:
    data = b""
    s.settimeout(3.0)
    try:
        while not data.endswith(b"\x04"):
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
    except socket.timeout:
        pass
    print(f"\n[{label}]")
    print(f"  raw bytes : {data!r}")
    print(f"  hex       : {data.hex()}")
    print(f"  text      : {data.decode('latin-1', errors='replace')!r}")
    return data


print(f"Connecting to {HOST}:{PORT}...")
s = socket.create_connection((HOST, PORT), timeout=10)

# --- Step 1: NS connect handshake ---
app = "FM BROWSER"
uci = "VAH"
connect_pkt = build_connect(app, uci)
print(f"\nSending connect packet ({len(connect_pkt)} bytes): {connect_pkt!r}")
s.sendall(connect_pkt)
time.sleep(0.3)
r1 = recv_all(s, "CONNECT ACK")

# --- Step 2: XUS SIGNON SETUP ---
rpc1 = build_rpc("XUS SIGNON SETUP")
print(f"\nSending XUS SIGNON SETUP: {rpc1!r}")
s.sendall(rpc1)
time.sleep(0.5)
r2 = recv_all(s, "XUS SIGNON SETUP response")

# --- Step 3: XUS AV CODE ---
# NOTE: VEHU demo credentials. The M code at VALIDAV+14^XUSRB expects AVCODE
# to be set from the parameter. If you see "Undefined local variable: AVCODE"
# that is a VistA M-level error — the broker received the packet but the
# credential decoding failed (likely needs encrypted format for this build).
creds = "fakedoc1;1Doc!@#$"
rpc2 = build_rpc("XUS AV CODE", [creds])
print(f"\nSending XUS AV CODE: {rpc2!r}")
try:
    s.sendall(rpc2)
    time.sleep(0.5)
    recv_all(s, "XUS AV CODE response")
except BrokenPipeError as e:
    print(f"\n[XUS AV CODE] BROKEN PIPE: {e}")
    print("  → broker closed the connection before we could send")

s.close()
print("\nDone.")
