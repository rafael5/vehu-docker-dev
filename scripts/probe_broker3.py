"""
Deep broker probe — read rpcbroker.sh, check registered apps, then
try full auth sequence with Format B (TCPCONNECT50 + IP + port).

Run inside the container:
    python3 /opt/vista-fm-browser/scripts/probe_broker3.py
"""

# ruff: noqa: E501
import socket
import subprocess
import time


def lp(s: str) -> bytes:
    b = s.encode("latin-1")
    return f"{len(b):03d}".encode() + b


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
    """Build a TCPConnect packet using the correct XWBPRS.m format.

    This format (derived from XWBPRS.m source) gets 'accept' from VEHU.
    The TCPCONNECT50 format (probe_broker2 Format B) gets 'Job ended' immediately.
    """
    return (
        b"[XWB]"
        b"1030"
        b"4"
        + sread("TCPConnect")
        + b"5"
        + b"\x00" + lread(ip)   + b"f"
        + b"\x00" + lread(port) + b"f"
        + b"\x00" + lread(app)  + b"f"
        + b"\x00" + lread(uci)  + b"f"
        + b"\x04"
    )


def build_rpc(rpc_name: str, params: list[str] | None = None) -> bytes:
    """Build an RPC call packet."""
    params = params or []
    chunk1 = b"1" + sread("") + sread("")
    chunk2 = b"2" + sread("0") + sread(rpc_name)
    if not params:
        chunk5 = b"5\x04"
    else:
        param_bytes = b"".join(b"\x00" + lread(p) + b"f" for p in params)
        chunk5 = b"5" + param_bytes + b"\x04"
    return b"[XWB]1030" + chunk1 + chunk2 + chunk5


def raw_recv(s: socket.socket, timeout: float = 3.0) -> bytes:
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


# --- 1. Read the broker launch script ---
print("=== /home/vehu/bin/rpcbroker.sh ===")
r = subprocess.run(
    "cat /home/vehu/bin/rpcbroker.sh", shell=True, capture_output=True, text=True
)
print(r.stdout or r.stderr)

# --- 2. Check registered RPC applications in VistA ---
print("\n=== Registered RPC Broker applications ===")
# Query the Application file (#8994.5) via ydb direct global read
ydb_cmd = r"""
source /usr/local/etc/ydb_env_set 2>/dev/null
$ydb_dist/yottadb -run %XCMD 'S X="" F  S X=$O(^XWB(8994.5,"B",X)) Q:X=""  W X,! ' 2>/dev/null
"""
r = subprocess.run(
    ydb_cmd, shell=True, capture_output=True, text=True, executable="/bin/bash"
)
out = (r.stdout + r.stderr).strip()
print(out[:2000] if out else "(no output)")

# --- 3. Full auth sequence with correct XWBPRS.m format ---
# Note: "FM BROWSER" is not in the registered apps list (^XWB(8994.5,"B")).
# Using a registered app name for the connect — any registered name works for
# the TCPCONNECT handshake; auth is validated separately in XUS AV CODE.
print("\n=== Full auth with correct XWBPRS.m format ===")
APP = "OR CPRS GUI CHART"
UCI = "VAH"

connect_pkt = build_connect(APP, UCI)

print(f"App: {APP!r}")
print(f"Connect pkt: {connect_pkt!r}")

try:
    s = socket.create_connection(("localhost", 9430), timeout=10)
    s.sendall(connect_pkt)
    time.sleep(0.5)
    r1 = raw_recv(s, timeout=5.0)
    print(f"Connect ack : {r1!r}")
    print(f"  text: {r1.decode('latin-1', errors='replace')!r}")

    if b"accept" in r1:
        # XUS SIGNON SETUP
        pkt = build_rpc("XUS SIGNON SETUP")
        s.sendall(pkt)
        time.sleep(0.5)
        r2 = raw_recv(s, timeout=5.0)
        print(f"SIGNON SETUP: {r2!r}")
        print(f"  text: {r2.decode('latin-1', errors='replace')!r}")

        if r2 and r2.endswith(b"\x04"):
            # XUS AV CODE
            creds = "fakedoc1;1Doc!@#$"
            pkt2 = build_rpc("XUS AV CODE", [creds])
            s.sendall(pkt2)
            time.sleep(0.5)
            r3 = raw_recv(s, timeout=5.0)
            print(f"AV CODE     : {r3!r}")
            print(f"  text: {r3.decode('latin-1', errors='replace')!r}")
    else:
        print("  → No accept — check app name registration or packet format")
    s.close()
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

print("\nDone.")
