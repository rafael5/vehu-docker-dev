"""
Tests for VistA RPC Broker client.

Unit tests use RpcFake — an in-memory server that speaks the XWB NS-mode
protocol over a real loopback TCP socket.  No container required.

Integration tests (marked @pytest.mark.integration) connect to the real
VEHU RPC Broker on localhost:9430 inside the container.
"""

import socketserver
import threading

import pytest

from vista_fm_browser.rpc_broker import (
    _XUSRB1_Z,
    EOT,
    GetsEntry,
    ListerEntry,
    RpcError,
    VistARpcBroker,
    _build_connect_packet,
    _build_list_param,
    _build_rpc_packet,
    _lread,
    _parse_response,
    _sread,
    _xusrb1_encrypt,
    parse_gets_response,
)

# ---------------------------------------------------------------------------
# Protocol helper unit tests (no networking)
# ---------------------------------------------------------------------------


class TestSread:
    def test_empty_string(self):
        result = _sread("")
        assert result == b"\x00"

    def test_single_char(self):
        result = _sread("A")
        assert result == b"\x01A"

    def test_rpc_name(self):
        result = _sread("XUS SIGNON SETUP")
        assert result[0] == 16
        assert result[1:] == b"XUS SIGNON SETUP"

    def test_length_byte_equals_string_length(self):
        s = "HELLO"
        result = _sread(s)
        assert result[0] == len(s)
        assert result[1:] == s.encode("latin-1")


class TestLread:
    def test_empty_string(self):
        assert _lread("") == b"000"

    def test_short_string(self):
        assert _lread("ABC") == b"003ABC"

    def test_longer_string(self):
        s = "XUS SIGNON SETUP"
        result = _lread(s)
        assert result == f"{len(s):03d}".encode() + s.encode()

    def test_three_digit_prefix(self):
        s = "X" * 120
        result = _lread(s)
        assert result[:3] == b"120"
        assert result[3:] == s.encode()


class TestBuildConnectPacket:
    def test_starts_with_xwb_magic(self):
        pkt = _build_connect_packet("MY APP", "VAH")
        assert pkt.startswith(b"[XWB]")

    def test_ends_with_eot(self):
        pkt = _build_connect_packet("MY APP", "VAH")
        assert pkt.endswith(EOT)

    def test_contains_tcp_connect(self):
        pkt = _build_connect_packet("FM BROWSER", "VAH")
        assert b"TCPConnect" in pkt

    def test_contains_app_name(self):
        pkt = _build_connect_packet("FM BROWSER", "VAH")
        assert b"FM BROWSER" in pkt

    def test_contains_uci(self):
        pkt = _build_connect_packet("APP", "VAH")
        assert b"VAH" in pkt

    def test_chunk4_marker_present(self):
        pkt = _build_connect_packet("APP", "VAH")
        assert b"4" in pkt  # chunk4 marker

    def test_chunk5_marker_present(self):
        pkt = _build_connect_packet("APP", "VAH")
        assert b"5" in pkt  # chunk5 marker


class TestBuildRpcPacket:
    def test_starts_with_xwb_magic(self):
        pkt = _build_rpc_packet("XWB GET VARIABLE VALUE", [])
        assert pkt.startswith(b"[XWB]")

    def test_ends_with_eot(self):
        pkt = _build_rpc_packet("XUS SIGNON SETUP", [])
        assert pkt.endswith(EOT)

    def test_contains_rpc_name(self):
        pkt = _build_rpc_packet("XUS AV CODE", ["test"])
        assert b"XUS AV CODE" in pkt

    def test_literal_param_value_present(self):
        pkt = _build_rpc_packet("MY RPC", ["hello"])
        assert b"hello" in pkt

    def test_multiple_params_all_present(self):
        pkt = _build_rpc_packet("MY RPC", ["first", "second", "third"])
        assert b"first" in pkt
        assert b"second" in pkt
        assert b"third" in pkt

    def test_no_params(self):
        pkt = _build_rpc_packet("XUS SIGNON SETUP", [])
        assert b"XUS SIGNON SETUP" in pkt
        assert pkt.endswith(EOT)

    def test_literal_ty_byte_is_ascii_zero(self):
        pkt = _build_rpc_packet("MY RPC", ["val"])
        # TY byte for literal param must be ASCII "0" (0x30), not chr(0)
        assert b"0003val" in pkt  # TY="0", lread("val")=003val

    def test_chunk2_marker_present(self):
        pkt = _build_rpc_packet("XUS SIGNON SETUP", [])
        assert b"2" in pkt  # chunk2 marker

    def test_chunk5_marker_present(self):
        pkt = _build_rpc_packet("XUS SIGNON SETUP", [])
        assert b"5" in pkt  # chunk5 marker


class TestBuildListParam:
    def test_empty_dict_sends_terminator(self):
        result = _build_list_param({})
        # TY=2, empty subscript, empty value, CONT=f
        assert result == b"2" + b"000" + b"000" + b"f"

    def test_single_item_has_cont_f(self):
        result = _build_list_param({"FILE": "2"})
        assert result.startswith(b"2")
        assert result.endswith(b"f")
        assert b"FILE" in result
        assert b"2" in result

    def test_multiple_items_middle_has_cont_t(self):
        result = _build_list_param({"FILE": "2", "IENS": "1,", "FIELDS": "*"})
        # First two entries should have 't' continuation
        # Last entry should have 'f'
        assert result.startswith(b"2")
        assert result.endswith(b"f")
        assert b"t" in result  # at least one non-final entry

    def test_ddr_gets_entry_data_subscripts_present(self):
        result = _build_list_param(
            {"FILE": "2", "IENS": "1,", "FIELDS": ".01", "FLAGS": ""}
        )
        assert b"FILE" in result
        assert b"IENS" in result
        assert b"FIELDS" in result
        assert b"FLAGS" in result

    def test_values_present(self):
        result = _build_list_param({"FILE": "50", "IENS": "3,"})
        assert b"50" in result
        assert b"3," in result

    def test_subscript_is_m_quoted(self):
        # Subscripts must be wrapped in M string quotes so LINST builds
        # a valid indirect reference: array("FILE") not array(FILE)
        result = _build_list_param({"FILE": "2"})
        # Subscript "FILE" → sent as '"FILE"' (6 chars) → LREAD prefix 006
        assert b'006"FILE"' in result

    def test_lread_prefix_on_value(self):
        # "2" is 1 char → LREAD prefix = b"001"
        result = _build_list_param({"FILE": "2"})
        assert b"001" + b"2" in result

    def test_single_item_no_t_byte(self):
        result = _build_list_param({"FILE": "2"})
        # Only one item — no "t" continuation byte anywhere
        assert b"t" not in result


class TestBuildRpcPacketWithListParam:
    def test_dict_param_produces_ty2(self):
        pkt = _build_rpc_packet("DDR GETS ENTRY DATA", [{"FILE": "2", "IENS": "1,"}])
        # TY=2 byte should appear in packet (as ASCII "2" after chunk5 marker)
        # chunk5 = b"5" then b"2" (list TY)
        assert b"5" in pkt
        assert b"FILE" in pkt
        assert b"IENS" in pkt

    def test_mixed_literal_and_list_params(self):
        pkt = _build_rpc_packet("SOME RPC", ["literal", {"KEY": "val"}])
        assert b"literal" in pkt
        assert b"KEY" in pkt
        assert b"val" in pkt

    def test_list_param_ends_before_eot(self):
        pkt = _build_rpc_packet("DDR GETS ENTRY DATA", [{"FILE": "2"}])
        assert pkt.endswith(EOT)


class TestParseResponse:
    def test_strips_nul_prefix_and_eot(self):
        raw = b"\x00\x00accept\x04"
        assert _parse_response(raw) == "accept"

    def test_strips_eot(self):
        raw = b"hello\x04"
        assert _parse_response(raw) == "hello"

    def test_multiline_response(self):
        raw = b"\x00\x00vehu\r\nROU\r\nVAH\r\n\x04"
        result = _parse_response(raw)
        assert "vehu" in result
        assert "VAH" in result

    def test_m_error_raises_rpc_error(self):
        raw = b"\x00\x00\x18M  ERROR=VALIDAV+14^XUSRB\x04"
        with pytest.raises(RpcError, match="VistA M error"):
            _parse_response(raw)

    def test_plain_text_no_nul(self):
        raw = b"plain response\x04"
        assert _parse_response(raw) == "plain response"

    def test_double_eot_stripped(self):
        # Some VistA responses end with \x04\x04
        raw = b"\x00\x00some data\x04\x04"
        result = _parse_response(raw)
        assert result == "some data"


class TestXusrb1Encrypt:
    def test_returns_string(self):
        enc = _xusrb1_encrypt("fakedoc1;1Doc!@#$")
        assert isinstance(enc, str)

    def test_first_byte_is_idix_plus_31(self):
        import random

        random.seed(42)
        enc = _xusrb1_encrypt("hello")
        idix = ord(enc[0]) - 31
        assert 1 <= idix <= 20

    def test_last_byte_is_associx_plus_31(self):
        import random

        random.seed(42)
        enc = _xusrb1_encrypt("hello")
        associx = ord(enc[-1]) - 31
        assert 1 <= associx <= 20

    def test_idix_not_equal_associx(self):
        import random

        random.seed(42)
        enc = _xusrb1_encrypt("hello")
        idix = ord(enc[0]) - 31
        associx = ord(enc[-1]) - 31
        assert idix != associx

    def test_roundtrip_with_decryp(self):
        """Verify that DECRYP(ENCRYP(s)) == s for the XUSRB1 cipher."""

        def decryp(s: str) -> str:
            if len(s) <= 2:
                return ""
            associx = ord(s[-1]) - 31
            idix = ord(s[0]) - 31
            assocstr = _XUSRB1_Z[associx - 1]
            idstr = _XUSRB1_Z[idix - 1]
            table = str.maketrans(assocstr, idstr)
            return s[1:-1].translate(table)

        for plaintext in ["fakedoc1;1Doc!@#$", "PRO1234;PRO1234!!", "hello world", "A"]:
            enc = _xusrb1_encrypt(plaintext)
            dec = decryp(enc)
            assert dec == plaintext, f"roundtrip failed for {plaintext!r}"

    def test_z_table_has_20_rows(self):
        assert len(_XUSRB1_Z) == 20

    def test_z_table_rows_are_94_chars(self):
        for i, row in enumerate(_XUSRB1_Z):
            assert len(row) == 94, f"row {i + 1} has length {len(row)}, expected 94"


# ---------------------------------------------------------------------------
# RpcFake — minimal TCP server that speaks XWB NS protocol
# ---------------------------------------------------------------------------


class _XwbFakeHandler(socketserver.BaseRequestHandler):
    """Handles one connection: accept NS hello, then respond to RPC calls."""

    CONNECT_ACK = b"\x00\x00accept\x04"

    RPC_RESPONSES: dict[str, bytes] = {
        "XUS SIGNON SETUP": b"\x00\x00VEHU Sign-on\x04",
        "XUS AV CODE": b"\x00\x001\r\n0\r\n0\r\n\r\n0\r\n0\r\n\x04",
        "XWB GET VARIABLE VALUE": b"\x00\x00foo\x04",
        "BYE": b"\x00\x00\x04",
        # DDR responses — format: file^iens^field^value per line
        "DDR GETS ENTRY DATA": (
            b"\x00\x002^1,^.01^SMITH,JOHN\r\n2^1,^.02^M\r\n2^1,^.03^2450101\r\n\x04"
        ),
        # format: total\r\nien^name\r\n...
        "DDR LISTER": b"\x00\x002\r\n1^SMITH,JOHN\r\n2^JONES,JANE\r\n\x04",
        # IEN string
        "DDR FIND1": b"\x00\x005\x04",
        # format: count\r\nien\r\n...
        "DDR FINDER": b"\x00\x002\r\n3\r\n7\r\n\x04",
    }
    DEFAULT_RESPONSE = b"\x00\x00OK\x04"

    def handle(self):
        # First receive the NS connect packet
        data = self._recv_packet()
        if b"TCPConnect" in data:
            self.request.sendall(self.CONNECT_ACK)

        # Now handle RPC calls until socket closes
        while True:
            try:
                data = self._recv_packet()
            except (ConnectionResetError, OSError):
                break
            if not data:
                break
            rpc_name = self._extract_rpc_name(data)
            resp = self.RPC_RESPONSES.get(rpc_name, self.DEFAULT_RESPONSE)
            self.request.sendall(resp)

    def _extract_rpc_name(self, data: bytes) -> str:
        """Extract the RPC name from a chunk-based XWB packet.

        In the new format, chunk2 is: b"2" + sread("0") + sread(rpc_name)
        where sread("0") = b"\\x010" (length=1, value="0").
        So chunk2 starts with b"2\\x010" then 1 byte of rpc_name length.
        """
        # Look for known RPC names directly as bytes (most reliable)
        for rpc_name in self.RPC_RESPONSES:
            if rpc_name.encode("latin-1") in data:
                return rpc_name
        # Fallback: try to parse chunk2 marker
        idx = data.find(b"2\x010")
        if idx >= 0 and idx + 4 < len(data):
            name_len = data[idx + 3]
            name_start = idx + 4
            return data[name_start : name_start + name_len].decode(
                "latin-1", errors="replace"
            )
        return ""

    def _recv_packet(self) -> bytes:
        data = b""
        while not data.endswith(EOT):
            chunk = self.request.recv(4096)
            if not chunk:
                return data
            data += chunk
        return data


class _ThreadedFakeServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


@pytest.fixture(scope="module")
def fake_rpc_server():
    """Start a fake VistA RPC Broker server on a random port."""
    server = _ThreadedFakeServer(("127.0.0.1", 0), _XwbFakeHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield ("127.0.0.1", port)
    server.shutdown()


# ---------------------------------------------------------------------------
# VistARpcBroker unit tests (against fake server)
# ---------------------------------------------------------------------------


class TestVistARpcBroker:
    def test_connect_and_close(self, fake_rpc_server):
        host, port = fake_rpc_server
        broker = VistARpcBroker(host=host, port=port)
        broker.connect(app="FM BROWSER", uci="VAH")
        broker.close()

    def test_context_manager(self, fake_rpc_server):
        host, port = fake_rpc_server
        with VistARpcBroker(host=host, port=port) as broker:
            broker.connect(app="FM BROWSER", uci="VAH")
        # No exception means __exit__ worked

    def test_call_signon_setup(self, fake_rpc_server):
        host, port = fake_rpc_server
        with VistARpcBroker(host=host, port=port) as broker:
            broker.connect(app="FM BROWSER", uci="VAH")
            result = broker.call("XUS SIGNON SETUP")
        assert result  # some non-empty response from fake server

    def test_call_with_params(self, fake_rpc_server):
        host, port = fake_rpc_server
        with VistARpcBroker(host=host, port=port) as broker:
            broker.connect(app="FM BROWSER", uci="VAH")
            result = broker.call("XWB GET VARIABLE VALUE", "^TMP")
        assert isinstance(result, str)

    def test_call_bye(self, fake_rpc_server):
        host, port = fake_rpc_server
        with VistARpcBroker(host=host, port=port) as broker:
            broker.connect(app="FM BROWSER", uci="VAH")
            broker.call("BYE")

    def test_not_connected_raises(self):
        broker = VistARpcBroker(host="127.0.0.1", port=9430)
        with pytest.raises(RuntimeError, match="not connected"):
            broker.call("XUS SIGNON SETUP")

    def test_connection_refused_raises(self):
        broker = VistARpcBroker(host="127.0.0.1", port=1)  # port 1 = refused
        with pytest.raises((ConnectionRefusedError, OSError)):
            broker.connect()


# ---------------------------------------------------------------------------
# parse_gets_response — pure function, no server needed
# ---------------------------------------------------------------------------


class TestParseGetsResponse:
    """parse_gets_response parses DDR GETS ENTRY DATA response lines.

    Each line has the form: file^iens^field^value
    Lines that don't match are skipped.  Empty lines are skipped.
    """

    def test_empty_string_returns_empty_list(self):
        assert parse_gets_response("") == []

    def test_parses_single_field(self):
        raw = "2^1,^.01^SMITH,JOHN\r\n"
        entries = parse_gets_response(raw)
        assert len(entries) == 1
        assert entries[0].file_number == 2.0
        assert entries[0].iens == "1,"
        assert entries[0].field_number == 0.01
        assert entries[0].value == "SMITH,JOHN"

    def test_parses_multiple_fields(self):
        raw = "2^1,^.01^SMITH,JOHN\r\n2^1,^.02^M\r\n2^1,^.03^2450101\r\n"
        entries = parse_gets_response(raw)
        assert len(entries) == 3

    def test_field_numbers_parsed_correctly(self):
        raw = "2^1,^.01^NAME\r\n2^1,^9999999^ICN_VALUE\r\n"
        entries = parse_gets_response(raw)
        by_field = {e.field_number: e for e in entries}
        assert 0.01 in by_field
        assert 9999999.0 in by_field

    def test_skips_empty_lines(self):
        raw = "2^1,^.01^SMITH,JOHN\r\n\r\n2^1,^.02^M\r\n"
        entries = parse_gets_response(raw)
        assert len(entries) == 2

    def test_skips_malformed_lines(self):
        raw = "not-a-valid-line\r\n2^1,^.01^SMITH,JOHN\r\n"
        entries = parse_gets_response(raw)
        assert len(entries) == 1

    def test_handles_lf_only_line_endings(self):
        raw = "2^1,^.01^SMITH,JOHN\n2^1,^.02^M\n"
        entries = parse_gets_response(raw)
        assert len(entries) == 2

    def test_value_with_caret_preserved(self):
        # Values can themselves contain carets
        raw = "2^1,^.01^LAST,FIRST^MIDDLE\r\n"
        entries = parse_gets_response(raw)
        assert len(entries) == 1
        assert entries[0].value == "LAST,FIRST^MIDDLE"

    def test_returns_gets_entry_objects(self):
        raw = "2^1,^.01^SMITH,JOHN\r\n"
        entries = parse_gets_response(raw)
        assert all(isinstance(e, GetsEntry) for e in entries)


# ---------------------------------------------------------------------------
# VistARpcBroker DDR methods — against fake server
# ---------------------------------------------------------------------------


class TestDdrMethods:
    def test_gets_entry_data_parsed_returns_entries(self, fake_rpc_server):
        host, port = fake_rpc_server
        with VistARpcBroker(host=host, port=port) as broker:
            broker.connect()
            entries = broker.gets_entry_data_parsed(file_number=2, ien="1")
        assert len(entries) == 3

    def test_gets_entry_data_parsed_field_values(self, fake_rpc_server):
        host, port = fake_rpc_server
        with VistARpcBroker(host=host, port=port) as broker:
            broker.connect()
            entries = broker.gets_entry_data_parsed(file_number=2, ien="1")
        by_field = {e.field_number: e for e in entries}
        assert by_field[0.01].value == "SMITH,JOHN"
        assert by_field[0.02].value == "M"

    def test_list_entries_returns_lister_entries(self, fake_rpc_server):
        host, port = fake_rpc_server
        with VistARpcBroker(host=host, port=port) as broker:
            broker.connect()
            entries = broker.list_entries(file_number=2)
        assert len(entries) == 2

    def test_list_entries_ien_and_value(self, fake_rpc_server):
        host, port = fake_rpc_server
        with VistARpcBroker(host=host, port=port) as broker:
            broker.connect()
            entries = broker.list_entries(file_number=2)
        assert entries[0].ien == "1"
        assert entries[0].external_value == "SMITH,JOHN"
        assert entries[1].ien == "2"
        assert entries[1].external_value == "JONES,JANE"

    def test_list_entries_returns_lister_entry_objects(self, fake_rpc_server):
        host, port = fake_rpc_server
        with VistARpcBroker(host=host, port=port) as broker:
            broker.connect()
            entries = broker.list_entries(file_number=2)
        assert all(isinstance(e, ListerEntry) for e in entries)

    def test_find_entry_returns_ien_string(self, fake_rpc_server):
        host, port = fake_rpc_server
        with VistARpcBroker(host=host, port=port) as broker:
            broker.connect()
            ien = broker.find_entry(file_number=2, value="SMITH,JOHN")
        assert ien == "5"

    def test_find_entries_returns_ien_list(self, fake_rpc_server):
        host, port = fake_rpc_server
        with VistARpcBroker(host=host, port=port) as broker:
            broker.connect()
            iens = broker.find_entries(file_number=2, value="SMITH")
        assert iens == ["3", "7"]


# ---------------------------------------------------------------------------
# Integration tests — run only inside VEHU container (port 9430 live)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRpcBrokerIntegration:
    """These tests require the VEHU container with the RPC Broker running.

    Inside the container:
        source /etc/yottadb/env
        pytest tests/ -m integration -v

    yottadb/octo-vehu credentials (DUZ=1, PROGRAMMER,ONE):
        Access code: PRO1234
        Verify code: PRO1234!!

    Override via environment variables:
        VEHU_ACCESS=PRO1234 VEHU_VERIFY="PRO1234!!" pytest tests/ -m integration
    """

    VEHU_HOST = "localhost"
    VEHU_PORT = 9430
    VEHU_APP = "FM BROWSER"
    VEHU_UCI = "VAH"
    import os as _os

    VEHU_ACCESS = _os.environ.get("VEHU_ACCESS", "PRO1234")
    VEHU_VERIFY = _os.environ.get("VEHU_VERIFY", "PRO1234!!")

    def _broker(self) -> VistARpcBroker:
        return VistARpcBroker(
            host=self.VEHU_HOST,
            port=self.VEHU_PORT,
            timeout=10.0,
        )

    def test_connect_to_vehu_broker(self):
        """Verify we can establish a TCP connection to the broker."""
        with self._broker() as broker:
            ack = broker.connect(app=self.VEHU_APP, uci=self.VEHU_UCI)
        assert "accept" in ack

    def test_signon_setup_returns_text(self):
        """XUS SIGNON SETUP should return intro/banner text."""
        with self._broker() as broker:
            broker.connect(app=self.VEHU_APP, uci=self.VEHU_UCI)
            result = broker.call("XUS SIGNON SETUP")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_authenticate_returns_duz(self):
        """XUS AV CODE with valid creds should return a numeric DUZ."""
        with self._broker() as broker:
            broker.connect(app=self.VEHU_APP, uci=self.VEHU_UCI)
            broker.call("XUS SIGNON SETUP")
            duz = broker.authenticate(self.VEHU_ACCESS, self.VEHU_VERIFY)
        assert duz, "DUZ should be non-empty on successful auth"
        assert duz.isdigit(), f"Expected numeric DUZ, got: {duz!r}"

    def test_get_variable_value(self):
        """XWB GET VARIABLE VALUE — retrieve a VistA M variable value."""
        with self._broker() as broker:
            broker.connect(app=self.VEHU_APP, uci=self.VEHU_UCI)
            broker.call("XUS SIGNON SETUP")
            broker.authenticate(self.VEHU_ACCESS, self.VEHU_VERIFY)
            result = broker.call("XWB GET VARIABLE VALUE", "$ZV")
        assert isinstance(result, str)

    def test_gets_entry_data_patient_file(self):
        """DDR GETS ENTRY DATA — read PATIENT file (file 2) entry IEN=1."""
        with self._broker() as broker:
            broker.connect(app=self.VEHU_APP, uci=self.VEHU_UCI)
            broker.call("XUS SIGNON SETUP")
            broker.authenticate(self.VEHU_ACCESS, self.VEHU_VERIFY)
            result = broker.gets_entry_data(file_number=2, ien="1", fields=".01")
        assert isinstance(result, str)
