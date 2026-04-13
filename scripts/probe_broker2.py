"""
Broker diagnostics — checks what's on port 9430 and tests multiple
connect packet formats to find what the VEHU broker expects.

Run inside the container:
    python3 /opt/vista-fm-browser/scripts/probe_broker2.py
"""

import socket
import subprocess
import time


def lp(s: str) -> bytes:
    """3-digit length prefix."""
    b = s.encode("latin-1")
    return f"{len(b):03d}".encode() + b


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


# --- 1. Check what process is on port 9430 ---
print("=== Port 9430 listener ===")
for cmd in [
    "netstat -tlnp 2>/dev/null | grep 9430",
    "lsof -i :9430 2>/dev/null",
    "cat /etc/xinetd.d/* 2>/dev/null",
    "ls /etc/xinetd.d/ 2>/dev/null",
]:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    out = (result.stdout + result.stderr).strip()
    if out:
        print(f"\n$ {cmd}")
        print(out[:500])

# --- 2. Listen first — does the server send a greeting? ---
print("\n=== Does the server send a greeting? ===")
try:
    s = socket.create_connection(("localhost", 9430), timeout=5)
    greeting = raw_recv(s, timeout=2.0)
    print(f"Server greeting (before we send anything): {greeting!r}")
    s.close()
except Exception as e:
    print(f"Error: {e}")

# --- 3. Test different connect packet formats ---
FORMATS = [
    # Format A: our current format
    (
        "A: [XWB]10304 TCPCONNECT5 lp(app) lp(uci)",
        b"[XWB]10304\nTCPCONNECT5\n" + lp("FM BROWSER") + lp("VAH") + b"\x04",
    ),
    # Format B: with IP and port included (some VistA versions require this)
    (
        "B: [XWB]10304 TCPCONNECT50 lp(ip) lp(port) lp(app) lp(uci)",
        b"[XWB]10304\nTCPCONNECT50\n"
        + lp("127.0.0.1")
        + lp("9430")
        + lp("FM BROWSER")
        + lp("VAH")
        + b"\x04",
    ),
    # Format C: leading NUL bytes (some ewd-vista style)
    (
        "C: 10xNUL + [XWB]10304 TCPCONNECT50 lp(app) lp(uci)",
        b"\x00" * 10
        + b"[XWB]10304\nTCPCONNECT50\n"
        + lp("FM BROWSER")
        + lp("VAH")
        + b"\x04",
    ),
    # Format D: try OR CPRS GUI CHART as app (definitely registered in VistA)
    (
        "D: CPRS app name with format A",
        b"[XWB]10304\nTCPCONNECT5\n" + lp("OR CPRS GUI CHART") + lp("VAH") + b"\x04",
    ),
    # Format E: no app/uci just raw connect
    ("E: minimal [XWB]10304 TCPCONNECT5 only", b"[XWB]10304\nTCPCONNECT5\n" + b"\x04"),
]

for label, pkt in FORMATS:
    print(f"\n--- {label} ---")
    print(f"  sending: {pkt!r}")
    try:
        s = socket.create_connection(("localhost", 9430), timeout=5)
        s.sendall(pkt)
        time.sleep(0.5)
        resp = raw_recv(s, timeout=2.0)
        print(f"  response: {resp!r}")
        if resp:
            print(f"  text    : {resp.decode('latin-1', errors='replace')!r}")
        s.close()
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")

print("\nDone.")
