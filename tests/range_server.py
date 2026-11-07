"""Server HTTP locale con supporto alle richieste a intervalli di byte (come S3 e data.ecmwf.int).

    python tests/range_server.py /tmp/fake 8765
"""
import http.server
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fake"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.translate_path(self.path.split("?")[0])
        if not os.path.isfile(path):
            self.send_error(404)
            return
        size = os.path.getsize(path)
        m = re.match(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
        with open(path, "rb") as f:
            if m:
                a = int(m.group(1))
                b = int(m.group(2)) if m.group(2) else size - 1
                f.seek(a)
                data = f.read(b - a + 1)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
            else:
                data = f.read()
                self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)


http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
