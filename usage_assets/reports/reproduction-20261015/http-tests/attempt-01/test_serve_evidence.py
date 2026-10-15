"""Real HTTP requests prove range bytes, headers and read-only path handling."""
import http.client
from pathlib import Path
import random
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from scripts.research import serve_evidence as server


class QuietHandler(server.EvidenceHandler):
    def log_message(self, *_):
        pass


@pytest.fixture
def evidence(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    content = random.Random(42).randbytes(257 * 128)
    (root / "sample.bin").write_bytes(content)
    (root / "empty.bin").touch()
    (root / "clip with spaces.bin").write_bytes(content)
    (root / ".git").mkdir()
    (root / ".git/config").write_text("metadata must stay hidden")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside the document root")
    (root / "escape.bin").symlink_to(outside)
    (root / "metadata-alias").symlink_to(root / ".git/config")
    httpd = server.make_server(root, port=0, handler=QuietHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield root, "http://127.0.0.1:" + str(httpd.server_port), content
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def request(base, path="/sample.bin", method="GET", headers=None, data=None):
    try:
        response = urlopen(Request(base + path, headers=headers or {}, method=method, data=data), timeout=5)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, response.read()


def test_get_and_head_stream_the_exact_file(evidence):
    _, base, content = evidence
    for method in ("GET", "HEAD"):
        status, headers, body = request(base, method=method)
        assert status == 200
        assert headers["Accept-Ranges"] == "bytes"
        assert int(headers["Content-Length"]) == len(content)
        assert body == (content if method == "GET" else b"")


@pytest.mark.parametrize("value,start,stop", [
    ("bytes=0-0", 0, 1), ("bytes=17-92", 17, 93), ("bytes=20-", 20, 257 * 128),
    ("bytes=-37", 257 * 128 - 37, 257 * 128), ("bytes=-999999", 0, 257 * 128),
    ("bytes=0-999999", 0, 257 * 128),
])
def test_bounded_open_ended_and_suffix_ranges(evidence, value, start, stop):
    _, base, content = evidence
    status, headers, body = request(base, headers={"Range": value})
    assert status == 206 and body == content[start:stop]
    assert headers["Content-Range"] == f"bytes {start}-{stop - 1}/{len(content)}"
    assert headers["Accept-Ranges"] == "bytes"
    assert int(headers["Content-Length"]) == stop - start


def test_head_range_has_get_headers_without_body(evidence):
    _, base, content = evidence
    status, headers, body = request(base, method="HEAD", headers={"Range": "bytes=17-92"})
    assert status == 206 and body == b""
    assert headers["Content-Range"] == f"bytes 17-92/{len(content)}"
    assert headers["Content-Length"] == "76"


@pytest.mark.parametrize("value", [
    "bytes=999999-", "bytes=91-17", "bytes=-0", "bytes=-", "bytes=0-1,2-3",
    "items=0-1", "bytes=not-a-number", "bytes=" + "9" * 5000 + "-",
])
def test_unsatisfiable_or_unsupported_ranges_return_416(evidence, value):
    _, base, content = evidence
    status, headers, body = request(base, headers={"Range": value})
    assert status == 416
    assert headers["Content-Range"] == f"bytes */{len(content)}"
    assert int(headers["Content-Length"]) == len(body) > 0


def test_duplicate_range_headers_are_not_silently_accepted(evidence):
    _, base, _ = evidence
    host, port = base.removeprefix("http://").split(":")
    with http.client.HTTPConnection(host, int(port), timeout=5) as connection:
        connection.putrequest("GET", "/sample.bin")
        connection.putheader("Range", "bytes=0-1")
        connection.putheader("Range", "bytes=4-5")
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == 416
        response.read()


def test_empty_file_and_if_range_mismatch(evidence):
    _, base, content = evidence
    status, headers, body = request(base, "/empty.bin")
    assert status == 200 and headers["Content-Length"] == "0" and body == b""
    status, headers, _ = request(base, "/empty.bin", headers={"Range": "bytes=0-"})
    assert status == 416 and headers["Content-Range"] == "bytes */0"
    status, headers, body = request(base, headers={"Range": "bytes=0-1", "If-Range": '"old-file"'})
    assert status == 200 and body == content and "Content-Range" not in headers


@pytest.mark.parametrize("path,status", [
    ("/%2e%2e/outside.bin", 403), ("/escape.bin", 403), ("/.git/config", 404),
    ("/metadata-alias", 404), ("/", 404), ("/%5c..%5coutside.bin", 403),
])
def test_escape_metadata_and_directory_listing_are_rejected(evidence, path, status):
    _, base, _ = evidence
    assert request(base, path)[0] == status


def test_encoded_names_and_post_do_not_change_files(evidence):
    root, base, content = evidence
    assert request(base, "/clip%20with%20spaces.bin?preview=1")[2] == content
    assert request(base, method="POST", data=b"replacement")[0] == 501
    assert (root / "sample.bin").read_bytes() == content


def test_actual_preserved_mp4_supports_media_range(evidence):
    root, base, _ = evidence
    original = Path(__file__).resolve().parents[1] / "usage_assets/isaac/official-pilot-quality/longest-original.mp4"
    data = original.read_bytes()
    (root / "actual.mp4").write_bytes(data)
    status, headers, body = request(base, "/actual.mp4", headers={"Range": "bytes=-128"})
    assert status == 206 and body == data[-128:]
    assert headers["Content-Type"] == "video/mp4"
    assert headers["Content-Range"] == f"bytes {len(data) - 128}-{len(data) - 1}/{len(data)}"
