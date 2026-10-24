"""Second local instance (port 8767) for parallel replay tails.

Decision log (2026-10-24, measured before the 1pm demo): the main batch
already uses ~2.9 of 16 logical cores (XNNPACK's internal thread pool), and
free RAM was only 2.8 GB - a second full model set would risk thrashing
the critical me2w tail, so this instance was NOT launched pre-demo. Kept
for later use when RAM frees up; the tail ran lean on the main server.
"""
from aiohttp import web

import gate1_server

app = gate1_server.build_app()
web.run_app(app, host="127.0.0.1", port=8767, print=None)
