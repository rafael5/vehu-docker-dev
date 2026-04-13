"""
Raw broker probe — prints exactly what the VEHU broker sends at each step.
Run inside the container:
    python3 /opt/vista-fm-browser/scripts/probe_broker.py
"""

import socket
import time

HOST = "localhost"
PORT = 9430


def lp(s: str) -> bytes:
    b = s.encode("latin-1")
    return f"{len(b):03d}".encode() + b


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
pkt = b"[XWB]10304\nTCPCONNECT5\n" + lp(app) + lp(uci) + b"\x04"
print(f"\nSending connect packet: {pkt!r}")
s.sendall(pkt)
time.sleep(0.3)
recv_all(s, "CONNECT ACK")

# --- Step 2: XUS SIGNON SETUP ---
rpc = "XUS SIGNON SETUP"
pkt2 = b"[XWB]11302\n" + lp(rpc) + b"\x000\x04"
print(f"\nSending XUS SIGNON SETUP: {pkt2!r}")
s.sendall(pkt2)
time.sleep(0.5)
recv_all(s, "XUS SIGNON SETUP response")

# --- Step 3: XUS AV CODE ---
creds = "fakedoc1;1Doc!@#$"
rpc2 = "XUS AV CODE"
pkt3 = b"[XWB]11302\n" + lp(rpc2) + b"\x00" + b"1" + b"0" + lp(creds) + b"\x04"
print(f"\nSending XUS AV CODE: {pkt3!r}")
try:
    s.sendall(pkt3)
    time.sleep(0.5)
    recv_all(s, "XUS AV CODE response")
except BrokenPipeError as e:
    print(f"\n[XUS AV CODE] BROKEN PIPE: {e}")
    print("  → broker closed the connection before we could send")

s.close()
print("\nDone.")
