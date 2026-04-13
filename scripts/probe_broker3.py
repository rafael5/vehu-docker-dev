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

# --- 3. Full auth sequence with Format B ---
print("\n=== Full auth with TCPCONNECT50 format ===")
APP = "OR CPRS GUI CHART"
UCI = "VAH"
IP = "127.0.0.1"
PORT = "9430"

connect_pkt = (
    b"[XWB]10304\nTCPCONNECT50\n" + lp(IP) + lp(PORT) + lp(APP) + lp(UCI) + b"\x04"
)

print(f"App: {APP!r}")
print(f"Connect pkt: {connect_pkt!r}")

try:
    s = socket.create_connection(("localhost", 9430), timeout=10)
    s.sendall(connect_pkt)
    time.sleep(0.5)
    r1 = raw_recv(s, timeout=5.0)
    print(f"Connect ack : {r1!r}")

    if r1:
        # XUS SIGNON SETUP
        rpc = "XUS SIGNON SETUP"
        pkt = b"[XWB]11302\n" + lp(rpc) + b"\x000\x04"
        s.sendall(pkt)
        time.sleep(0.5)
        r2 = raw_recv(s, timeout=5.0)
        print(f"SIGNON SETUP: {r2!r}")
        print(f"  text: {r2.decode('latin-1', errors='replace')!r}")

        if r2:
            # XUS AV CODE
            creds = "fakedoc1;1Doc!@#$"
            rpc2 = "XUS AV CODE"
            pkt2 = b"[XWB]11302\n" + lp(rpc2) + b"\x001" + b"0" + lp(creds) + b"\x04"
            s.sendall(pkt2)
            time.sleep(0.5)
            r3 = raw_recv(s, timeout=5.0)
            print(f"AV CODE     : {r3!r}")
            print(f"  text: {r3.decode('latin-1', errors='replace')!r}")
    s.close()
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

print("\nDone.")
