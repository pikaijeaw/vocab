#!/usr/bin/env python3
"""Static server for the vocab dashboard (HSK + TOEIC). Usage: python3 serve.py [port] [--host 127.0.0.1]"""
import argparse, functools, http.server, os

p = argparse.ArgumentParser()
p.add_argument("port", nargs="?", type=int, default=5005)
p.add_argument("--host", default="127.0.0.1")
a = p.parse_args()
root = os.path.dirname(os.path.abspath(__file__))
class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # always revalidate so phones/tablets pick up dashboard + data updates
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


H = functools.partial(Handler, directory=root)
print(f"Vocab dashboard running at http://{a.host}:{a.port}/  (Ctrl+C to stop)")
http.server.ThreadingHTTPServer((a.host, a.port), H).serve_forever()
