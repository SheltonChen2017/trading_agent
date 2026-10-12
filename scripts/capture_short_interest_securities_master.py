"""One prospective source-only full Sharadar master; no prices or QC.

Signed bulk URLs are ephemeral capabilities: held in memory, never printed,
persisted or hashed. Only the fixed authenticated issuer can supply one.
"""
from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
from pathlib import Path
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.sharadar_companion_qualification as old
import research.short_interest_etf.sharadar_securities_master as master
from scripts.qualify_finra_short_interest import (
    CapturePlatformRefusal, CaptureRefusal, _NoRedirect, _git,
    _prepare_capture_directory, _publish, _publish_json, _require_capture_platform,
)
from scripts.qualify_sharadar_companion import (
    CREDENTIAL_PATH, SharadarCaptureRefusal, _guard, _http, _read_key,
    _refuse_credential_echo, _utc_now,
)
from scripts.qualify_short_interest_action_supplement import _clock

CAPTURE_PARENT = Path("artifacts/short_interest/sharadar_securities_master")
METADATA_MAX = 65536
SCHEMA_MAX = 131072
REPORT_MAX = 512 * 1024 * 1024
MAX_ATTEMPTS = 12


class MasterCaptureRefusal(CaptureRefusal):
    def __init__(self, code: str, *, status=None):
        super().__init__(code)
        self.code = code
        self.http_status = status if type(status) is int and 100 <= status <= 599 else None


def _protocol() -> dict:
    value = master.qualification_protocol()
    if (hash_payload(value) != master.PROTOCOL_SHA256 or value["maximum_requests"] != MAX_ATTEMPTS
            or tuple(value["request_ids"]) != master.REQUEST_IDS or len(master.REQUEST_IDS) != MAX_ATTEMPTS
            or value["requests"] != [master.sharadar_master_request(rid) for rid in master.REQUEST_IDS]):
        raise MasterCaptureRefusal("frozen_master_inventory")
    return value


def _metadata(raw: bytes, table: str, now: str) -> dict:
    """Reuse the already verified selected-full inventory validator."""
    payload = old._json(raw)
    if type(payload) is not dict or payload.get("table") != table:
        raise MasterCaptureRefusal("metadata_table")
    fields = {"history", "historyLabel", "name", "size", "sizeLabel", "modified", "available"}
    if "files" in payload:
        old._keys(payload, {"table", "files"}, fields)
        if type(payload["files"]) is not list or not 1 <= len(payload["files"]) <= 3:
            raise MasterCaptureRefusal("metadata_inventory")
        inventory = {}
        for entry in payload["files"]:
            checked = old._metadata_file(entry, table, _clock(now), inventory=True)
            if checked["history"] in inventory:
                raise MasterCaptureRefusal("metadata_inventory")
            inventory[checked["history"]] = checked
        if "full" not in inventory:
            raise MasterCaptureRefusal("metadata_full_history")
        selected = inventory["full"]
        top = {key: item for key, item in payload.items() if key not in {"table", "files"}}
        if top and old._metadata_file(top, table, _clock(now), inventory=True) != {
                key: item for key, item in selected.items() if key != "key"}:
            raise MasterCaptureRefusal("metadata_selected_inventory")
    else:
        old._keys(payload, {"table", "name", "size", "sizeLabel", "modified"}, {"history", "historyLabel", "available"})
        selected = old._metadata_file({key: item for key, item in payload.items() if key != "table"},
                                      table, _clock(now), inventory=False)
    if (selected.get("available") is False or type(selected["size"]) is not int
            or not 22 <= selected["size"] <= master.MAXIMUM_ARCHIVE_BYTES):
        raise MasterCaptureRefusal("selected_archive_unavailable_or_size_limit")
    return {"size": selected["size"], "modified": selected["modified"]}


def _issuer_location(opener, request, key: str) -> str:
    _require_capture_platform()
    response = None
    try:
        try:
            response = opener.open(request, timeout=30)
        except urllib.error.HTTPError as exc:
            response = exc
        status = getattr(response, "status", None)
        if type(status) is not int or status != 302:
            raise MasterCaptureRefusal("bulk_issuer_not_302", status=status)
        locations = response.headers.get_all("Location")
        if type(locations) is not list or len(locations) != 1 or type(locations[0]) is not str:
            raise MasterCaptureRefusal("bulk_location_ambiguous", status=status)
        location = locations[0]
        if len(location) > 16384 or any(ord(char) < 33 or ord(char) > 126 for char in location):
            raise MasterCaptureRefusal("bulk_location_shape", status=status)
        if key in urllib.parse.unquote(urllib.parse.unquote(location)):
            raise MasterCaptureRefusal("credential_echo", status=status)
        return location
    except (urllib.error.URLError, OSError, TimeoutError, ConnectionError):
        raise MasterCaptureRefusal("bulk_issuer_network") from None
    finally:
        if response is not None:
            response.close()  # Never read, print, hash or retain the redirect body.


def _refuse_capability_echo(raw: bytes, content_type: str, location: str) -> None:
    """Reject response echoes before any capability-derived bytes are hashed.

    Whole URLs and query pairs are always protected. Long query values and
    named short credentials/signatures are also protected independently; short
    nonsecret expiry numbers are not banned from unrelated source cells.
    """
    candidates = {location, urllib.parse.unquote(location),
                  urllib.parse.unquote(urllib.parse.unquote(location))}
    parsed = urllib.parse.urlsplit(location)
    for component in parsed.path.split("/"):
        if len(component) >= 16:
            candidates.add(component)
    for name, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
        candidates.add(name + "=" + value)
        sensitive_name = re.search(r"(?:^|[-_])(?:token|signature|credential|secret|key|sig|ephemeral)(?:$|[-_])", name, re.I)
        if value and (len(value) >= 16 or sensitive_name):
            candidates.add(value)
    variants = set()
    for item in candidates:
        if item:
            value = item.encode("utf-8")
            for _ in range(3):
                variants.add(value)
                value = urllib.parse.unquote_to_bytes(value)
    def checked(buffer):
        for _ in range(3):
            if any(needle in buffer for needle in variants):
                raise MasterCaptureRefusal("signed_capability_echo", status=200)
            buffer = urllib.parse.unquote_to_bytes(buffer)
    for buffer in (raw, content_type.encode("utf-8")):
        checked(buffer)
        # Inspect string tokens before persistence, including Unicode/slash
        # escapes; bytes percent-decoding above also accepts lowercase escapes.
        for token in re.finditer(rb'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"', buffer):
            try:
                decoded = json.loads(token.group().decode("utf-8")).encode("utf-8")
            except (UnicodeError, ValueError):
                continue
            checked(decoded)


def _public_unicast(value) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return (address.is_global and not address.is_multicast and not address.is_unspecified
            and not address.is_reserved and not address.is_loopback and not address.is_link_local)


def _public_addresses(location: str, resolve=socket.getaddrinfo):
    _require_capture_platform()
    parsed = urllib.parse.urlsplit(location)
    try:
        port = parsed.port
    except ValueError:
        raise MasterCaptureRefusal("download_origin") from None
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.fragment or port not in (None, 443)
            or re.fullmatch(r"[A-Za-z0-9.-]+(?::443)?", parsed.netloc) is None
            or parsed.hostname.startswith(".") or parsed.hostname.endswith(".")):
        raise MasterCaptureRefusal("download_origin")
    try:
        addresses = resolve(parsed.hostname, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise MasterCaptureRefusal("download_DNS") from None
    if not addresses:
        raise MasterCaptureRefusal("download_DNS")
    checked = []
    for family, kind, proto, _, address in addresses:
        public = _public_unicast(address[0])
        if (family not in (socket.AF_INET, socket.AF_INET6) or kind != socket.SOCK_STREAM
                or proto not in (0, socket.IPPROTO_TCP) or not public or address[1] != 443):
            raise MasterCaptureRefusal("download_nonpublic_destination")
        if (family, address) not in checked:
            checked.append((family, address))
    # Deterministic IPv4 preference; no hidden alternative connection/retry.
    checked.sort(key=lambda item: (item[0] != socket.AF_INET, item[1][0]))
    return parsed, checked[0]


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, hostname: str, target, *, context):
        super().__init__(hostname, 443, timeout=30, context=context)
        self._target = target

    def connect(self):
        _require_capture_platform()
        if self._context.check_hostname is not True or self._context.verify_mode != ssl.CERT_REQUIRED:
            raise MasterCaptureRefusal("download_TLS_verification_required")
        family, address = self._target
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            sock.settimeout(self.timeout)
            sock.connect(address)
            observed = ipaddress.ip_address(sock.getpeername()[0])
            if not _public_unicast(str(observed)) or observed != ipaddress.ip_address(address[0]):
                raise MasterCaptureRefusal("download_peer_changed")
            # Normal CA and hostname verification, even though TCP uses a
            # previously validated numeric address to prevent DNS rebinding.
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def _download(location: str, key: str) -> tuple[bytes, str, int]:
    _require_capture_platform()
    parsed, target = _public_addresses(location)
    connection = _PinnedHTTPS(parsed.hostname, target, context=ssl.create_default_context())
    try:
        path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        connection.request("GET", path, headers={"Accept": "application/zip, application/octet-stream"})
        response = connection.getresponse()
        if type(response.status) is not int or response.status != 200:
            raise MasterCaptureRefusal("download_not_200", status=response.status)
        content_type = response.getheader("Content-Type", "")
        if (type(content_type) is not str or len(content_type) > 256
                or key in urllib.parse.unquote(content_type)
                or response.getheader("Content-Encoding", "identity").lower() != "identity"):
            raise MasterCaptureRefusal("download_header_contract", status=200)
        length = response.getheader("Content-Length")
        if length is not None and (re.fullmatch(r"[0-9]{1,12}", length) is None
                                   or int(length) > master.MAXIMUM_ARCHIVE_BYTES):
            raise MasterCaptureRefusal("download_size_limit", status=200)
        raw = response.read(master.MAXIMUM_ARCHIVE_BYTES + 1)
        if len(raw) > master.MAXIMUM_ARCHIVE_BYTES or (length is not None and len(raw) != int(length)):
            raise MasterCaptureRefusal("download_size_or_truncation", status=200)
        return raw, content_type, 200
    except (OSError, TimeoutError, ConnectionError, http.client.HTTPException):
        raise MasterCaptureRefusal("download_network") from None
    finally:
        connection.close()


def _claim(directory: Path, head: str, remote: str, started: str) -> None:
    _require_capture_platform()
    try:
        _publish_json(directory.parent, "budget-" + master.PROTOCOL_SHA256 + ".json", {
            "schema": "si-sharadar-master-whole-round-budget-v1", "run_id": directory.name,
            "protocol_sha256": master.PROTOCOL_SHA256, "code_head": head, "remote_head": remote,
            "maximum_attempts": MAX_ATTEMPTS, "started_at": started, "resumption_allowed": False,
        })
    except (CaptureRefusal, FileExistsError):
        raise MasterCaptureRefusal("whole_round_budget_claimed") from None


def _capture(root: Path, directory: Path, key: str, opener, *, head: str, remote: str) -> dict:
    _require_capture_platform()
    protocol = _protocol()
    archives, metadata, location = [], {}, None
    previous_clock = _clock(_utc_now())
    for ordinal, rid in enumerate(master.REQUEST_IDS, 1):
        _guard(root, head, remote)
        spec = master.sharadar_master_request(rid)
        if ordinal > MAX_ATTEMPTS or spec != protocol["requests"][ordinal - 1]:
            raise MasterCaptureRefusal("request_budget_or_binding")
        kind, table = rid.split("-", 1)
        started = _utc_now()
        if _clock(started) < previous_clock:
            raise MasterCaptureRefusal("capture_clock_reversed")
        prefix = f"attempt-{ordinal:02d}"
        _publish_json(directory, prefix + ".started.json", {
            "schema": "si-sharadar-master-request-start-v1", "attempt": ordinal,
            "request_id": rid, "request": spec, "request_sha256": master.request_sha256(rid),
            "code_head": head, "protocol_sha256": master.PROTOCOL_SHA256, "started_at": started,
        })
        status = None
        try:
            _guard(root, head, remote)
            if kind == "download":
                if location is None:
                    raise MasterCaptureRefusal("download_without_issuer")
                raw, ctype, status = _download(location, key)
                if key.encode() in raw:
                    raise MasterCaptureRefusal("credential_echo", status=status)
                _refuse_capability_echo(raw, ctype, location)
                csv_bytes = master.validate_archive(table, raw)
                _refuse_credential_echo(csv_bytes, ctype, key, status)
                _refuse_capability_echo(csv_bytes, ctype, location)
                location = None
            else:
                url = spec["url"] + "?" + urllib.parse.urlencode(spec["params"])
                parsed = urllib.parse.urlsplit(spec["url"])
                if (parsed.scheme != "https" or parsed.netloc != "api.sharadar.com"
                        or parsed.path != "/v1.0/" + ("schema/" if kind == "schema" else "data/") + table
                        or parsed.query or parsed.fragment):
                    raise MasterCaptureRefusal("issuer_origin")
                headers = {"Accept": "text/plain" if kind == "schema" else "application/json"}
                if kind != "schema":
                    headers["x-api-key"] = key
                request = urllib.request.Request(url, headers=headers, method="GET")
                if kind == "issue":
                    location = _issuer_location(opener, request, key)
                    # Early structural origin refusal before a second request.
                    parsed = urllib.parse.urlsplit(location)
                    if parsed.scheme != "https" or parsed.hostname is None:
                        raise MasterCaptureRefusal("download_origin", status=302)
                    raw, ctype, status = None, None, 302
                else:
                    raw, ctype, status = _http(opener, request, METADATA_MAX if kind == "metadata" else SCHEMA_MAX)
                    _refuse_credential_echo(raw, ctype, key, status)
            received = _utc_now()
            if _clock(received) < _clock(started):
                raise MasterCaptureRefusal("capture_clock_reversed", status=status)
            previous_clock = _clock(received)
            if raw is not None:
                _publish(directory, prefix + ".raw", raw)
            _publish_json(directory, prefix + ".received.json", {
                "schema": "si-sharadar-master-response-receipt-v1", "attempt": ordinal,
                "request_id": rid, "request_sha256": master.request_sha256(rid),
                "http_status": status, "content_type": ctype,
                "raw_path": None if raw is None else prefix + ".raw",
                "raw_bytes": None if raw is None else len(raw),
                "raw_sha256": None if raw is None else hash_bytes(raw),
                "received_at": received, "signed_URL_persisted_or_hashed": False,
            })
            if kind == "metadata":
                metadata[table] = _metadata(raw, table, received)
            elif kind == "schema":
                if ("CREATE TABLE" not in raw.decode("utf-8")
                        or re.search(r"\b" + table + r"\b", raw.decode("utf-8"), re.I) is None):
                    raise MasterCaptureRefusal("public_schema_contract", status=status)
            elif kind == "download":
                # Validated, key-checked bytes/receipt survive a metadata race;
                # an invalid or key-echoing archive is deliberately withheld.
                if len(raw) != metadata[table]["size"]:
                    raise MasterCaptureRefusal("archive_metadata_size_changed", status=status)
                archives.append(master.CapturedSharadarMasterArchive(table, raw, master.request_sha256(rid)))
        except (CaptureRefusal, ValueError, KeyError) as exc:
            location = None
            safe = type(exc) in (MasterCaptureRefusal, SharadarCaptureRefusal)
            code = exc.code if safe else "response_contract_or_guard_refused"
            observed = exc.http_status if safe else status
            _publish_json(directory, prefix + ".refused.json", {
                "schema": "si-sharadar-master-request-refusal-v1", "attempt": ordinal,
                "request_id": rid, "code": code, "http_status": observed, "refused_at": _utc_now(),
            })
            raise MasterCaptureRefusal(code, status=observed) from None
    retrieved = _utc_now()
    if _clock(retrieved) < previous_clock:
        raise MasterCaptureRefusal("capture_clock_reversed")
    report = master.qualify_sharadar_securities_master(tuple(archives), retrieved_at=retrieved)
    payload = report.to_payload()
    encoded = (canonical_json(payload) + "\n").encode()
    if len(encoded) > REPORT_MAX:
        raise MasterCaptureRefusal("private_report_size_limit")
    _publish_json(directory, "master.private.json", payload)
    _guard(root, head, remote)
    result = {"schema": "si-sharadar-master-capture-completion-v1", "status": "capture_complete",
              "protocol_sha256": master.PROTOCOL_SHA256, "code_head": head, "http_attempts": MAX_ATTEMPTS,
              "private_report_sha256": report.sha256, "completed_at": _utc_now(),
              "outcome_looks_consumed": 0, "qc_launch_attempts": 0, "backtest_result_exists": False}
    _publish_json(directory, "completed.json", result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-remote", required=True)
    args = parser.parse_args(argv)
    directory = None
    try:
        _require_capture_platform()
        root = Path.cwd().resolve()
        _guard(root, args.expected_head, args.expected_remote)
        protocol = _protocol()
        started = _utc_now()
        run_id = "sharadar-master-" + _clock(started).strftime("%Y%m%dT%H%M%SZ")
        target = root / CAPTURE_PARENT / run_id
        if _git(root, "check-ignore", str(target)) != str(target):
            raise MasterCaptureRefusal("capture_not_ignored")
        key = _read_key(CREDENTIAL_PATH)
        directory = _prepare_capture_directory(target)
        _claim(directory, args.expected_head, args.expected_remote, started)
        _publish_json(directory, "protocol.json", protocol)
        _publish_json(directory, "started.json", {
            "schema": "si-sharadar-master-capture-start-v1", "run_id": run_id, "started_at": started,
            "code_head": args.expected_head, "remote_head": args.expected_remote,
            "protocol_sha256": master.PROTOCOL_SHA256, "maximum_attempts": MAX_ATTEMPTS,
            "source_only": True, "outcome_looks_consumed": 0, "qc_launch_attempts": 0,
        })
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        result = _capture(root, directory, key, opener, head=args.expected_head, remote=args.expected_remote)
    except (CaptureRefusal, ValueError, OSError, KeyError, UnicodeError) as exc:
        safe = type(exc) in (CapturePlatformRefusal, MasterCaptureRefusal, SharadarCaptureRefusal)
        result = {"status": "capture_refused", "code": exc.code if safe else "local_preflight_refused",
                  "http_status": exc.http_status if safe else None, "backtest_result_exists": False}
        if type(exc) is CapturePlatformRefusal:
            result["ready_for_empirical_backtest"] = False
        if directory is not None:
            _publish_json(directory, "refused.json", {**result, "refused_at": _utc_now(),
                "outcome_looks_consumed": 0, "qc_launch_attempts": 0})
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
