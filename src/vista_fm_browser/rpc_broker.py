"""
VistA RPC Broker TCP client (XWB NS-mode, Kernel 8.0).

Executes Remote Procedure Calls against a running VistA instance over TCP.
The VEHU container exposes the broker on port 9430 (localhost inside container,
or the host-mapped port from docker-compose.yml).

XWB NS-mode protocol overview
------------------------------
Wire format derived from XWBPRS.m and XWBTCPMT.m source analysis.

PRSP header (4 bytes after [XWB] magic):
    ver(1) type(1) lenv(1) rt(1)
    e.g. "1030" → ver=1, type=0, lenv=3, rt=0

SREAD encoding: 1-byte ASCII length prefix + value
    _sread("ABC") → b"\\x03ABC"

LREAD encoding: lenv-digit decimal length prefix + value  (lenv=3)
    _lread("ABC") → b"003ABC"

Chunk types (read by PRSM):
    "1" → PRS1: ver + return_type (both SREAD)
    "2" → PRS2: rpc_ver + rpc_name (both SREAD)
    "4" → PRS4: command (SREAD)
    "5" → PRS5: params — each: TY(1) + LREAD(value) + CONT(1), ends at TY=\\x04

PRS5 param TY values (CRITICAL: must be ASCII digit strings, NOT chr(0)):
    "0" → literal string parameter
    "4" → empty parameter
    \\x04 → EOT (end of params)

Connection handshake packet:
    [XWB]1030  (magic + PRSP)
    4 + SREAD("TCPConnect")   (chunk4: command)
    5                         (chunk5: params)
    + "0" + LREAD(ip)  + "f"
    + "0" + LREAD(port) + "f"
    + "0" + LREAD(app)  + "f"
    + "0" + LREAD(uci)  + "f"
    + \\x04                    (EOT)

RPC call packet:
    [XWB]1030  (magic + PRSP)
    1 + SREAD("") + SREAD("")   (chunk1: empty ver + return)
    2 + SREAD("0") + SREAD(rpc_name)  (chunk2: rpc)
    5 + ["0" + LREAD(param) + "f" ...] + \\x04  (chunk5: params)

Response from server:
    \\x00\\x00 {data} \\x04
    The two leading NUL bytes are stripped; \\x04 is stripped from the tail.
    M errors arrive as \\x00\\x00\\x18M  ERROR=...\\x04

Credentials must be encrypted with ENCRYP^XUSRB1 before sending to
XUS AV CODE; VALIDAV always decrypts before checking.

Sign-on sequence:
    1. broker.connect(app, uci)           → NS handshake (→ "accept")
    2. broker.call("XUS SIGNON SETUP")    → intro text
    3. broker.authenticate(access, verify) → DUZ on success

Example::

    with VistARpcBroker(host="localhost", port=9430) as broker:
        broker.connect(app="FM BROWSER", uci="VAH")
        broker.call("XUS SIGNON SETUP")
        duz = broker.authenticate("fakedoc1", "1Doc!@#$")
        data = broker.gets_entry_data(file_number=2, ien="1", fields=".01")

VEHU demo credentials
---------------------
    Access code: fakedoc1
    Verify code: 1Doc!@#$
    UCI:         VAH
    RPC Broker port: 9430
"""

import logging
import random
import socket
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Protocol constants
# ------------------------------------------------------------------

EOT = b"\x04"
NUL = b"\x00"

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9430
DEFAULT_APP = "FM BROWSER"
DEFAULT_UCI = "VAH"
DEFAULT_TIMEOUT = 10.0
RECV_SIZE = 8192

# ------------------------------------------------------------------
# XUSRB1 encryption — Z lookup table (20 rows, each 94 chars)
# Extracted from /home/vehu/r/XUSRB1.m Z+1 through Z+20 via
#   $P($T(Z+N), ";", 3, 9)
# Each row is a random permutation of printable ASCII (32-126) minus "^"
# ------------------------------------------------------------------

_XUSRB1_Z: list[str] = [  # noqa: E501 — cipher table rows are 94-char data literals
    "wkEo-ZJt!dG)49K{nX1BS$vH<&:Myf*>Ae0jQW=;|#PsO`'%+rmb[gpqN,l6/hFC@DcUa ]z~R}\"V\\iIxu?872.(TYL5_3",  # noqa: E501
    "rKv`R;M/9BqAF%&tSs#Vh)dO1DZP> *fX'u[.4lY=-mg_ci802N7LTG<]!CWo:3?{+,5Q}(@jaExn$~p\\IyHwzU\"|k6Jeb",  # noqa: E501
    "\\pV(ZJk\"WQmCn!Y,y@1d+~8s?[lNMxgHEt=uw|X:qSLjAI*}6zoF{T3#;ca)/h5%`P4$r]G'9e2if_>UDKb7<v0&- RBO.",  # noqa: E501
    "depjt3g4W)qD0V~NJar\\B \"?OYhcu[<Ms%Z`RIL_6:]AX-zG.#}$@vk7/5x&*m;(yb2Fn+l'PwUof1K{9,|EQi>H=CT8S!",  # noqa: E501
    "NZW:1}K$byP;jk)7'`x90B|cq@iSsEnu,(l-hf.&Y_?J#R]+voQXU8mrV[!p4tg~OMez CAaGFD6H53%L/dT2<*>\"{\\wI=",  # noqa: E501
    "vCiJ<oZ9|phXVNn)m K`t/SI%]A5qOWe\\&?;jT~M!fz1l>[D_0xR32c*4.P\"G{r7}E8wUgyudF+6-:B=$(sY,LkbHa#'@Q",  # noqa: E501
    "hvMX,'4Ty;[a8/{6l~F_V\"}qLI\\!@x(D7bRmUH]W15J%N0BYPkrs&9:$)Zj>u|zwQ=ieC-oGA.#?tfdcO3gp`S+En K2*<",  # noqa: E501
    "jd!W5[];4'<C$/&x|rZ(k{>?ghBzIFN}fAK\"#`p_TqtD*1E37XGVs@0nmSe+Y6Qyo-aUu%i8c=H2vJ\\) R:MLb.9,wlO~P",  # noqa: E501
    "2ThtjEM+!=xXb)7,ZV{*ci3\"8@_l-HS69L>]\\AUF/Q%:qD?1~m(yvO0e'<#o$p4dnIzKP|`NrkaGg.ufCRB[; sJYwW}5&",  # noqa: E501
    "vB\\5/zl-9y:Pj|=(R'7QJI *&CTX\"p0]_3.idcuOefVU#omwNZ`$Fs?L+1Sk<,b)hM4A6[Y%aDrg@~KqEW8t>H};n!2xG{",  # noqa: E501
    "sFz0Bo@_HfnK>LR}qWXV+D6`Y28=4Cm~G/7-5A\\b9!a#rP.l&M$hc3ijQk;),TvUd<[:I\"u1'NZSOw]*gxtE{eJp|y (?%",  # noqa: E501
    "M@,D}|LJyGO8`$*ZqH .j>c~h<d=fimszv[#-53F!+a;NC'6T91IV?(0x&/{B)w\"]Q\\YUWprk4:ol%g2nE7teRKbAPuS_X",  # noqa: E501
    ".mjY#_0*H<B=Q+FML6]s;r2:e8R}[ic&KA 1w{)vV5d,$u\"~xD/Pg?IyfthO@CzWp%!`N4Z'3-(o|J9XUE7k\\TlqSb>anG",  # noqa: E501
    "xVa1']_GU<X`|\\NgM?LS9{\"jT%s$}y[nvtlefB2RKJW~(/cIDCPow4,>#zm+:5b@06O3Ap8=*7ZFY!H-uEQk; .q)i&rhd",  # noqa: E501
    "I]Jz7AG@QX.\"%3Lq>METUo{Pp_ |a6<0dYVSv8:b)~W9NK`(r'4fs&wim\\kReC2hg=HOj$1B*/nxt,;c#y+![?lFuZ-5D}",  # noqa: E501
    "Rr(Ge6F Hx>q$m&C%M~Tn,:\"o'tX/*yP.{lZ!YkiVhuw_<KE5a[;}W0gjsz3]@7cI2\\QN?f#4p|vb1OUBD9)=-LJA+d`S8",  # noqa: E501
    "I~k>y|m};d)-7DZ\"Fe/Y<B:xwojR,Vh]O0Sc[`$sg8GXE!1&Qrzp._W%TNK(=J 3i*2abuHA4C'?Mv\\Pq{n#56LftUl@9+",  # noqa: E501
    "~A*>9 WidFN,1KsmwQ)GJM{I4:C%}#Ep(?HB/r;t.&U8o|l['Lg\"2hRDyZ5`nbf]qjc0!zS-TkYO<_=76a\\X@$Pe3+xVvu",  # noqa: E501
    "yYgjf\"5VdHc#uA,W1i+v'6|@pr{n;DJ!8(btPGaQM.LT3oe?NB/&9>Z`-}02*%x<7lsqz4OS ~E$\\R]KI[:UwC_=h)kXmF",  # noqa: E501
    "5:iar.{YU7mBZR@-K|2 \"+~`M%8sq4JhPo<_X\\Sg3WC;Tuxz,fvEQ1p9=w}FAI&j/keD0c?)LN6OHV]lGy'$*>nd[(tb!#",  # noqa: E501
]


# ------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------


class RpcError(Exception):
    """Raised when the VistA broker returns an application-level error."""


# ------------------------------------------------------------------
# Data structures for parsed DDR responses
# ------------------------------------------------------------------


@dataclass
class GetsEntry:
    """One field value returned by DDR GETS ENTRY DATA / GETS^DIQ.

    Attributes
    ----------
    file_number:
        FileMan file number the field belongs to.
    iens:
        Internal Entry Number String identifying the record (e.g. "1,").
    field_number:
        FileMan field number.
    value:
        External value as returned by VistA (or internal if "I" flag used).
    """

    file_number: float
    iens: str
    field_number: float
    value: str


@dataclass
class ListerEntry:
    """One entry returned by DDR LISTER.

    Attributes
    ----------
    ien:
        Internal entry number (string).
    external_value:
        The display value — typically the .01 field in external format.
    extra_fields:
        Any additional field values included in the response.
    """

    ien: str
    external_value: str
    extra_fields: dict[str, str] = field(default_factory=dict)


# ------------------------------------------------------------------
# DDR response parsers (pure functions — no network required)
# ------------------------------------------------------------------


def parse_gets_response(raw: str) -> list[GetsEntry]:
    """Parse the raw string from DDR GETS ENTRY DATA into GetsEntry objects.

    Expected line format (one field per line, CRLF or LF separated):

        file^iens^field^value

    Lines that do not have at least four caret-separated pieces are skipped.
    Values can themselves contain carets; everything after the third caret
    is treated as the value.

    Parameters
    ----------
    raw:
        The string returned by ``VistARpcBroker.call("DDR GETS ENTRY DATA", ...)``
        or ``VistARpcBroker.gets_entry_data(...)``.

    Returns
    -------
    list[GetsEntry]
        One entry per successfully-parsed line.

    Note
    ----
    The exact wire format of DDR GETS ENTRY DATA varies across VistA
    versions.  Verify against a live VEHU instance before relying on
    the parsed output for production code.
    """
    entries: list[GetsEntry] = []
    for line in raw.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("^", 3)  # split into at most 4 parts
        if len(parts) < 4:
            continue
        try:
            file_num = float(parts[0])
            field_num = float(parts[2])
        except ValueError:
            continue
        entries.append(
            GetsEntry(
                file_number=file_num,
                iens=parts[1],
                field_number=field_num,
                value=parts[3],
            )
        )
    return entries


def _parse_lister_response(raw: str) -> list[ListerEntry]:
    """Parse the raw string from DDR LISTER into ListerEntry objects.

    Expected format::

        total_count\\r\\nien^external_value[^field...]\\r\\n...

    The first line is the total count (discarded); each following line is one
    entry.  The first caret-piece is the IEN, the second is the display value,
    and any further pieces are additional field values.
    """
    entries: list[ListerEntry] = []
    lines = raw.replace("\r\n", "\n").split("\n")
    # Skip the first line (total count) and empty lines
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split("^")
        ien = parts[0]
        external_value = parts[1] if len(parts) > 1 else ""
        extra_fields = {str(i): parts[i] for i in range(2, len(parts)) if parts[i]}
        entries.append(
            ListerEntry(
                ien=ien, external_value=external_value, extra_fields=extra_fields
            )
        )
    return entries


def _parse_finder_response(raw: str) -> list[str]:
    """Parse the raw string from DDR FINDER into a list of IEN strings.

    Expected format::

        total_count\\r\\nien\\r\\nien\\r\\n...

    The first line (total count) is discarded.
    """
    lines = raw.replace("\r\n", "\n").split("\n")
    return [ln.strip() for ln in lines[1:] if ln.strip()]


# ------------------------------------------------------------------
# Protocol helpers (pure functions — easy to test)
# ------------------------------------------------------------------


def _sread(s: str) -> bytes:
    """SREAD encoding: 1-byte ASCII length + value.

    e.g. "XUS SIGNON SETUP" → b"\\x10XUS SIGNON SETUP"
    """
    b = s.encode("latin-1")
    assert len(b) < 256, f"sread value too long: {s!r}"
    return bytes([len(b)]) + b


def _lread(s: str) -> bytes:
    """LREAD encoding: 3-digit decimal length prefix + value.

    e.g. "PATIENT" → b"007PATIENT"
    """
    b = s.encode("latin-1")
    return f"{len(b):03d}".encode() + b


def _build_connect_packet(
    app: str,
    uci: str,
    ip: str = "127.0.0.1",
    port: str = "0",
) -> bytes:
    """Build the NS-mode TCP connection handshake packet.

    Uses chunk-based format derived from XWBPRS.m / XWBTCPMT.m:
        [XWB]1030  chunk4(TCPConnect)  chunk5(ip port app uci)  EOT

    PRS5 TY byte is ASCII "0" (literal param type).  Using \\x00 (chr 0)
    instead would fail the `IF TY=0` check in PRS5 which is a MUMPS
    string comparison matching ASCII "0", not chr(0).
    """
    return (
        b"[XWB]"
        b"1030"  # PRSP: ver=1, type=0, lenv=3, rt=0
        b"4"
        + _sread("TCPConnect")  # chunk4: command
        + b"5"  # chunk5: params
        + b"0"
        + _lread(ip)
        + b"f"
        + b"0"
        + _lread(port)
        + b"f"
        + b"0"
        + _lread(app)
        + b"f"
        + b"0"
        + _lread(uci)
        + b"f"
        + EOT
    )


def _build_list_param(items: dict[str, str]) -> bytes:
    """Build a TY=2 (list-type) parameter for PRS5 chunk5.

    Used by DDR RPCs that pass a local M array as a parameter
    (e.g. DDR GETS ENTRY DATA passes DDR("FILE"), DDR("IENS"), etc.).

    Wire format: TY=b"2", then subscript-value pairs each followed by a
    CONT byte: b"t" (more pairs) or b"f" (last pair, signals end of list).
    After b"f", PRS5 reads the next TY byte.

    Subscripts are wrapped in M string quotes (e.g. "FILE" → '"FILE"') so
    that LINST^XWBPRS can use M indirection correctly:
        S @(array_name_"("_subscript_")")=value
    Without quotes, M treats the subscript as a local variable reference
    (e.g. FILE instead of "FILE"), causing an LVUNDEF error.

    Parameters
    ----------
    items:
        Ordered dict of ``{subscript: value}`` pairs.  Insertion order is
        preserved (Python 3.7+).  An empty dict sends a single empty-pair
        terminator.  Subscripts are plain Python strings (no embedded
        quotes needed — this function adds them).
    """
    if not items:
        return b"2" + _lread("") + _lread("") + b"f"
    pairs = list(items.items())
    result = b"2"
    for i, (subscript, value) in enumerate(pairs):
        cont = b"f" if i == len(pairs) - 1 else b"t"
        # Wrap subscript in M string quotes so LINST builds a valid
        # indirect reference: array("FILE") not array(FILE)
        m_subscript = f'"{subscript}"'
        result += _lread(m_subscript) + _lread(value) + cont
    return result


def _build_rpc_packet(rpc_name: str, params: list[str | dict[str, str]]) -> bytes:
    """Build an RPC call packet.

    Parameters
    ----------
    rpc_name:
        Name of the VistA RPC (e.g. "XUS SIGNON SETUP").
    params:
        List of parameters.  Each element is either:
        - ``str`` — a literal string parameter (TY=b"0")
        - ``dict[str, str]`` — a list-type array parameter (TY=b"2"),
          e.g. ``{"FILE": "2", "IENS": "1,", "FIELDS": "*", "FLAGS": ""}``
    """
    chunk1 = b"1" + _sread("") + _sread("")  # empty ver + return_type
    chunk2 = b"2" + _sread("0") + _sread(rpc_name)  # rpc_ver + rpc_name
    if not params:
        chunk5 = b"5" + EOT  # immediate EOT
    else:
        param_bytes = b""
        for p in params:
            if isinstance(p, dict):
                param_bytes += _build_list_param(p)  # TY="2" list param
            else:
                param_bytes += b"0" + _lread(p) + b"f"  # TY="0" literal
        param_bytes += EOT
        chunk5 = b"5" + param_bytes
    return b"[XWB]1030" + chunk1 + chunk2 + chunk5


def _parse_response(raw: bytes) -> str:
    """Parse a broker response packet into a plain string.

    The server sends: \\x00\\x00 {content} \\x04
    Strips the two leading NUL bytes and the trailing EOT.
    Raises RpcError if the response contains a broker M error.
    """
    data = raw.rstrip(EOT)
    text = data.lstrip(NUL).decode("latin-1", errors="replace")
    # M errors arrive as chr(24) + "M  ERROR=..."
    if text.startswith("\x18") or "M  ERROR=" in text:
        raise RpcError(f"VistA M error: {text!r}")
    return text


def _xusrb1_encrypt(plaintext: str) -> str:
    """Encrypt a string using the ENCRYP^XUSRB1 substitution cipher.

    VistA's XUS AV CODE RPC passes credentials through DECRYP^XUSRB1
    before checking them, so the client must encrypt first.

    Algorithm (mirrors ENCRYP^XUSRB1 in M):
      1. Pick a random associator index and a different identifier index
         (both in 1-20).
      2. Look up their rows in the Z+ substitution table.
      3. Translate each character in plaintext: chars found in the
         identifier row are replaced by the corresponding char in the
         associator row.
      4. Wrap the result: chr(idix+31) + translated + chr(associx+31)
    """
    associx = random.randint(1, 20)
    idix = associx
    while idix == associx:
        idix = random.randint(1, 20)
    assocstr = _XUSRB1_Z[associx - 1]
    idstr = _XUSRB1_Z[idix - 1]
    table = str.maketrans(idstr, assocstr)
    return chr(idix + 31) + plaintext.translate(table) + chr(associx + 31)


# ------------------------------------------------------------------
# Broker client
# ------------------------------------------------------------------


class VistARpcBroker:
    """VistA RPC Broker TCP client (XWB NS mode).

    Usage::

        with VistARpcBroker(host="localhost", port=9430) as broker:
            broker.connect(app="FM BROWSER", uci="VAH")
            broker.call("XUS SIGNON SETUP")
            duz = broker.authenticate("fakedoc1", "1Doc!@#$")
            result = broker.call("XWB GET VARIABLE VALUE", "$ZV")
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._sock: socket.socket | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(
        self,
        app: str = DEFAULT_APP,
        uci: str = DEFAULT_UCI,
    ) -> str:
        """Open the TCP connection and perform the NS-mode handshake.

        Parameters
        ----------
        app:
            Application name sent in the handshake (e.g. "FM BROWSER").
            VistA logs this; use a descriptive name.
        uci:
            UCI (Universal Computer Identifier), e.g. "VAH" for VEHU.

        Returns the server's acknowledgement text (usually "accept").
        Raises RpcError if the server rejects the connection.
        """
        self._sock = socket.create_connection(
            (self._host, self._port), timeout=self._timeout
        )
        log.debug("Connected to VistA broker at %s:%d", self._host, self._port)
        pkt = _build_connect_packet(app, uci)
        self._sock.sendall(pkt)
        raw = self._recv()
        ack = raw.rstrip(EOT).lstrip(NUL).decode("latin-1", errors="replace")
        log.debug("Broker handshake: %r", ack)
        if "accept" not in ack:
            raise RpcError(f"Broker rejected connection: {ack!r}")
        return ack

    def close(self) -> None:
        """Send BYE and close the TCP connection."""
        if self._sock is not None:
            try:
                pkt = _build_rpc_packet("BYE", [])
                self._sock.sendall(pkt)
            except OSError:
                pass
            finally:
                self._sock.close()
                self._sock = None
                log.debug("VistA broker connection closed")

    def __enter__(self) -> "VistARpcBroker":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # RPC execution
    # ------------------------------------------------------------------

    def call(self, rpc_name: str, *params: str | dict[str, str]) -> str:
        """Execute a VistA RPC and return the response as a string.

        Parameters
        ----------
        rpc_name:
            VistA RPC name (e.g. "XUS SIGNON SETUP", "DDR GETS ENTRY DATA").
        *params:
            Parameters for the RPC.  Each is either a ``str`` (literal, TY=0)
            or a ``dict[str, str]`` (list-type array, TY=2).

        Raises RuntimeError if not connected.
        Raises RpcError if the broker returns an error response.
        """
        if self._sock is None:
            raise RuntimeError("not connected — call connect() first")
        pkt = _build_rpc_packet(rpc_name, list(params))
        self._sock.sendall(pkt)
        raw = self._recv()
        log.debug("RPC %r → %d bytes", rpc_name, len(raw))
        return _parse_response(raw)

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------

    def authenticate(self, access_code: str, verify_code: str) -> str:
        """Authenticate with VistA access/verify codes.

        Encrypts the credentials with ENCRYP^XUSRB1 (matching what CPRS
        clients do), calls XUS AV CODE, and returns the DUZ string on
        success.

        Must be called after connect() and after XUS SIGNON SETUP.

        Raises RpcError if authentication fails or VistA returns DUZ=0.
        """
        plaintext = f"{access_code};{verify_code}"
        encrypted = _xusrb1_encrypt(plaintext)
        result = self.call("XUS AV CODE", encrypted)
        log.debug("XUS AV CODE result: %r", result)
        # Response: DUZ is RET(0), first line of the multi-line result.
        # A DUZ > 0 means success.
        duz_line = result.split("\r\n")[0].strip()
        try:
            duz = int(duz_line)
        except ValueError:
            raise RpcError(f"Authentication failed: {result!r}")
        if duz <= 0:
            raise RpcError(f"Authentication failed (DUZ={duz}): {result!r}")
        return duz_line

    def gets_entry_data(
        self,
        file_number: int | float,
        ien: str,
        fields: str = "*",
        flags: str = "",
    ) -> str:
        """Fetch field data for a FileMan entry via DDR GETS ENTRY DATA.

        Wraps the ``GETS^DIQ`` DBS call.  Returns the raw response string
        from VistA; use ``gets_entry_data_parsed()`` for structured output.

        Parameters
        ----------
        file_number:
            FileMan file number (e.g. 2 for PATIENT, 50 for DRUG).
        ien:
            Internal entry number, e.g. "1" or "1,2," for a subfile entry.
        fields:
            Caret-separated field numbers, or:
            "*"  = all top-level fields
            "**" = all fields including sub-multiple entries
        flags:
            DDR flags: "I" = return internal values, "E" = return external
            values, "N" = omit null values, "R" = resolve field names.

        Returns the raw response string (format: "file^iens^field^value" per line).
        """
        if self._sock is None:
            raise RuntimeError("not connected — call connect() first")
        fn = (
            str(int(file_number))
            if file_number == int(file_number)
            else str(file_number)
        )
        # FileMan IENS requires a trailing comma for single-level entries ("1,")
        iens = ien if ien.endswith(",") else ien + ","
        # DDR GETS ENTRY DATA passes params as a local M array (TY=2 list type)
        # via GETSC(DDRDATA, DDR) in DDR2.m — not as 4 literal TY=0 params
        pkt = _build_rpc_packet(
            "DDR GETS ENTRY DATA",
            [{"FILE": fn, "IENS": iens, "FIELDS": fields, "FLAGS": flags}],
        )
        self._sock.sendall(pkt)
        raw = self._recv()
        log.debug("RPC DDR GETS ENTRY DATA → %d bytes", len(raw))
        return _parse_response(raw)

    def gets_entry_data_parsed(
        self,
        file_number: int | float,
        ien: str,
        fields: str = "*",
        flags: str = "",
    ) -> list[GetsEntry]:
        """Fetch and parse field data for a FileMan entry.

        Calls ``DDR GETS ENTRY DATA`` and parses the response into
        :class:`GetsEntry` objects.

        Parameters are identical to :meth:`gets_entry_data`.

        Returns
        -------
        list[GetsEntry]
            One entry per field returned.  Field numbers and values are
            typed.  Values are in external format unless the "I" flag is set.
        """
        raw = self.gets_entry_data(
            file_number=file_number, ien=ien, fields=fields, flags=flags
        )
        return parse_gets_response(raw)

    def list_entries(
        self,
        file_number: int | float,
        *,
        xref: str = "B",
        value: str = "",
        from_value: str = "",
        part: bool = False,
        max_entries: int = 44,
        screen: str = "",
        identifier: str = "",
        fields: str = "",
        flags: str = "",
    ) -> list[ListerEntry]:
        """List entries from a FileMan file via DDR LISTER.

        Wraps the ``LIST^DIC`` DBS call through the DDR LISTER RPC.
        Supports cross-reference navigation, partial matching, and screening.

        Parameters
        ----------
        file_number:
            FileMan file number.
        xref:
            Cross-reference to use for ordering (default "B" = name index).
        value:
            Value to match or start from in the cross-reference.
        from_value:
            Start listing from this value (for pagination).  Use the last
            ``external_value`` from a previous call to page forward.
        part:
            If True, match entries whose index value starts with ``value``
            (partial/prefix match).
        max_entries:
            Maximum entries to return (default 44 matches the CPRS standard).
        screen:
            M boolean expression to filter entries, e.g. screening by sex field.
        identifier:
            M expression appended to each entry's display value.
        fields:
            Caret-separated field numbers to include in the response beyond
            the default identifier.
        flags:
            Additional DDR flags.

        Returns
        -------
        list[ListerEntry]
            Entries in cross-reference order.

        Note
        ----
        Parameter order and exact names for DDR LISTER vary across VistA
        versions.  Verify against a live VEHU instance.
        """
        fn = (
            str(int(file_number))
            if file_number == int(file_number)
            else str(file_number)
        )
        raw = self.call(
            "DDR LISTER",
            fn,
            fields,
            flags,
            str(max_entries),
            from_value,
            "1" if part else "0",
            value,
            xref,
            screen,
            identifier,
        )
        return _parse_lister_response(raw)

    def find_entry(
        self,
        file_number: int | float,
        value: str,
        *,
        xref: str = "B",
        screen: str = "",
    ) -> str:
        """Find a single entry by value via DDR FIND1.

        Wraps the ``$$FIND1^DIC`` DBS call.  Returns the IEN string of the
        first entry whose cross-reference value matches ``value``, or an
        empty string if not found.

        Parameters
        ----------
        file_number:
            FileMan file number.
        value:
            Exact value to search for in the cross-reference.
        xref:
            Cross-reference to search (default "B" = name index).
        screen:
            M boolean expression to filter candidates.

        Returns
        -------
        str
            IEN of the matching entry, or "" if not found.
        """
        fn = (
            str(int(file_number))
            if file_number == int(file_number)
            else str(file_number)
        )
        return self.call("DDR FIND1", fn, value, xref, screen).strip()

    def find_entries(
        self,
        file_number: int | float,
        value: str,
        *,
        xref: str = "B",
        screen: str = "",
        flags: str = "",
        max_entries: int = 44,
    ) -> list[str]:
        """Find multiple entries by value via DDR FINDER.

        Wraps the ``FIND^DIC`` DBS call.  Returns IEN strings for all
        entries whose cross-reference value starts with ``value``.

        Parameters
        ----------
        file_number:
            FileMan file number.
        value:
            Value (or prefix) to search for.
        xref:
            Cross-reference to search (default "B").
        screen:
            M boolean expression to filter candidates.
        flags:
            DDR flags ("M" = multiple matches allowed, etc.).
        max_entries:
            Maximum IENs to return.

        Returns
        -------
        list[str]
            IEN strings for all matching entries.

        Note
        ----
        Parameter order for DDR FINDER may vary.  Verify against live VEHU.
        """
        fn = (
            str(int(file_number))
            if file_number == int(file_number)
            else str(file_number)
        )
        raw = self.call(
            "DDR FINDER",
            fn,
            xref,
            "",  # from_value
            "1",  # part (prefix match)
            value,
            str(max_entries),
            screen,
            flags,
        )
        return _parse_finder_response(raw)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _recv(self) -> bytes:
        """Read from the socket until EOT (\\x04) is received."""
        assert self._sock is not None
        data = b""
        while not data.endswith(EOT):
            try:
                chunk = self._sock.recv(RECV_SIZE)
            except socket.timeout as exc:
                raise TimeoutError(
                    f"Timed out waiting for broker response after {self._timeout}s"
                ) from exc
            if not chunk:
                break
            data += chunk
        return data
