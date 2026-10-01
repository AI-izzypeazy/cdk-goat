"""Stdlib HTTP server exposing the crawler as a JSON API + the dashboard UI.

No web framework required — runs on a stock Python install. Each crawl runs in
its own background thread with a dedicated asyncio loop, so the API stays
responsive and the dashboard can poll /api/status for live progress.

API:
  POST /api/crawl   {config...}      -> {job_id}
  GET  /api/status?job=ID            -> live snapshot
  GET  /api/report?job=ID            -> full report (+ catalogue sample)
  POST /api/stop?job=ID              -> stop a running job
  GET  /api/jobs                     -> list recent jobs
  GET  /                             -> dashboard
"""
from __future__ import annotations

import asyncio
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import CrawlConfig
from .crawler import Crawler

_UI_DIR = Path(__file__).parent / "ui"


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict = {}
        self._lock = threading.Lock()

    def start(self, cfg: CrawlConfig) -> str:
        job_id = uuid.uuid4().hex[:12]
        crawler = Crawler(cfg)

        def runner():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(crawler.run())
            finally:
                loop.close()

        thread = threading.Thread(target=runner, daemon=True)
        with self._lock:
            self._jobs[job_id] = {"crawler": crawler, "thread": thread,
                                  "url": cfg.start_url}
        thread.start()
        return job_id

    def get(self, job_id: str):
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list:
        with self._lock:
            return [
                {"job_id": jid, "url": j["url"],
                 "status": j["crawler"].state.status,
                 "pages": j["crawler"].state.pages_fetched,
                 "products": len(j["crawler"].catalogue.products)}
                for jid, j in reversed(list(self._jobs.items()))
            ][:25]


JOBS = JobManager()


class Handler(BaseHTTPRequestHandler):
    server_version = "CrawlStreet/1.0"

    def log_message(self, fmt, *args):  # quieter console
        pass

    # --- helpers ----------------------------------------------------------
    def _json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, ctype: str):
        if not path.exists():
            self._json({"error": "not found"}, 404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return {}

    def _query(self) -> dict:
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    # --- routes -----------------------------------------------------------
    def do_GET(self):
        route = urlparse(self.path).path
        if route in ("/", "/index.html"):
            return self._file(_UI_DIR / "index.html", "text/html; charset=utf-8")
        if route == "/app.js":
            return self._file(_UI_DIR / "app.js", "application/javascript")
        if route == "/styles.css":
            return self._file(_UI_DIR / "styles.css", "text/css")
        if route == "/api/jobs":
            return self._json({"jobs": JOBS.list()})
        if route == "/api/status":
            job = JOBS.get(self._query().get("job", ""))
            if not job:
                return self._json({"error": "unknown job"}, 404)
            return self._json(job["crawler"].snapshot())
        if route == "/api/report":
            job = JOBS.get(self._query().get("job", ""))
            if not job:
                return self._json({"error": "unknown job"}, 404)
            return self._json(job["crawler"].full_report())
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        route = urlparse(self.path).path
        if route == "/api/crawl":
            data = self._body()
            url = (data.get("start_url") or "").strip()
            if not url.startswith(("http://", "https://")):
                return self._json({"error": "start_url must be an http(s) URL"}, 400)
            cfg = CrawlConfig.from_dict(data)
            cfg.start_url = url
            job_id = JOBS.start(cfg)
            return self._json({"job_id": job_id})
        if route == "/api/stop":
            job = JOBS.get(self._query().get("job", ""))
            if not job:
                return self._json({"error": "unknown job"}, 404)
            job["crawler"].stop()
            return self._json({"stopped": True})
        return self._json({"error": "not found"}, 404)


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"\n  Crawl Street dashboard →  http://{host}:{port}\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down.")
        httpd.shutdown()
