#!/usr/bin/env python3
"""Serve repository evidence locally with byte ranges for video seeking."""
from __future__ import annotations

import argparse
from functools import partial
import http.server
import os
from pathlib import Path
import re
import stat
from urllib.parse import unquote, urlsplit, urlunsplit

REPOSITORY = Path(__file__).resolve().parents[2]
BLOCK_BYTES = 64 * 1024


def byte_range(value: str, size: int) -> tuple[int, int]:
    """Return inclusive bounds for one satisfiable HTTP bytes range."""
    match = re.fullmatch(r"bytes=([0-9]*)-([0-9]*)", value.strip())
    if match is None or not any(match.groups()) or size <= 0:
        raise ValueError("One nonempty bytes range is required")
    first, last = match.groups()
    if not first:
        suffix = int(last)
        if suffix <= 0:
            raise ValueError("Suffix must be positive")
        return max(0, size - suffix), size - 1
    start = int(first)
    end = int(last) if last else size - 1
    if start >= size or end < start:
        raise ValueError("Range is outside the file")
    return start, min(end, size - 1)


class EvidenceHandler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, directory: str, **kwargs):
        self.root = Path(directory).resolve()
        self.remaining = 0
        super().__init__(*args, directory=str(self.root), **kwargs)

    def evidence_path(self) -> Path:
        path = unquote(urlsplit(self.path).path, errors="strict")
        parts = [part for part in path.split("/") if part]
        if "\\" in path or ".." in parts:
            raise PermissionError("Path traversal is not allowed")
        if any(part.startswith(".") for part in parts):
            raise FileNotFoundError("Hidden metadata is not served")
        target = self.root.joinpath(*parts).resolve()
        if not target.is_relative_to(self.root):
            raise PermissionError("Path is outside the evidence root")
        if any(part.startswith(".") for part in target.relative_to(self.root).parts):
            raise FileNotFoundError("Hidden metadata is not served")
        return target

    def range_error(self, size: int):
        body = b"Requested byte range is not satisfiable.\n"
        self.send_response(416)
        self.send_header("Content-Range", f"bytes */{size}")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        return None

    def send_head(self):
        try:
            target = self.evidence_path()
            if target.is_dir():
                # Allow explicit HTML entry pages; never enumerate directories.
                index = next((target / name for name in ("index.html", "index.htm")
                              if (target / name).is_file()), None)
                if index is None:
                    raise FileNotFoundError("Directory listing is disabled")
                if not urlsplit(self.path).path.endswith("/"):
                    parsed = urlsplit(self.path)
                    self.send_response(301)
                    self.send_header("Location", urlunsplit(parsed._replace(path=parsed.path + "/")))
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return None
                target = index.resolve()
                if not target.is_relative_to(self.root):
                    raise PermissionError("Index is outside the evidence root")
            source = target.open("rb")
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode):
                source.close()
                raise FileNotFoundError("Only regular evidence files are served")
        except PermissionError:
            self.send_error(403, "Path is outside the evidence root")
            return None
        except (FileNotFoundError, IsADirectoryError):
            self.send_error(404, "Evidence file not found")
            return None
        except (UnicodeError, ValueError):
            self.send_error(400, "Invalid request path")
            return None
        size = info.st_size
        ranges = self.headers.get_all("Range", [])
        etag = f'"{info.st_mtime_ns:x}-{size:x}"'
        modified = self.date_time_string(info.st_mtime)
        if self.headers.get("If-Range") not in (None, etag, modified):
            ranges = []
        try:
            if len(ranges) > 1:
                raise ValueError("Multiple ranges are unsupported")
            start, end = byte_range(ranges[0], size) if ranges else (0, size - 1)
        except ValueError:
            source.close()
            return self.range_error(size)
        self.remaining = end - start + 1
        source.seek(start)
        self.send_response(206 if ranges else 200)
        self.send_header("Content-Type", self.guess_type(str(target)))
        self.send_header("Content-Length", str(self.remaining))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Last-Modified", modified)
        self.send_header("ETag", etag)
        if ranges:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        return source

    def copyfile(self, source, outputfile):
        try:
            while self.remaining:
                data = source.read(min(BLOCK_BYTES, self.remaining))
                if not data:
                    break
                outputfile.write(data)
                self.remaining -= len(data)
        except (BrokenPipeError, ConnectionResetError):
            # Browsers cancel old video ranges when the user seeks again.
            pass


def make_server(directory=REPOSITORY, bind="127.0.0.1", port=8088, handler=EvidenceHandler):
    root = Path(directory).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("An existing evidence directory is required")
    return http.server.ThreadingHTTPServer((bind, port), partial(handler, directory=str(root)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=REPOSITORY)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args()
    with make_server(args.directory, args.bind, args.port) as server:
        host, port = server.server_address
        print(f"Serving evidence from {Path(args.directory).resolve()} at http://{host}:{port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
