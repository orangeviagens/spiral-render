"""
Spiral Studios — HTTP API Server

Lightweight HTTP server for n8n webhook integration.
Uses Python stdlib (no FastAPI needed — works anywhere).

For production VPS, replace with FastAPI version (see server_fastapi.py).

Endpoints:
    POST /render         — Full pipeline: generate script + narration + video
    POST /render/script  — Render from provided script JSON + narration URL
    GET  /status/:id     — Check render status
    GET  /health         — Health check
"""
import json
import os
import threading
import time
import uuid
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict
from urllib.parse import urlparse, parse_qs

from . import config
from .pipeline import ProductionPipeline

logger = logging.getLogger("spiral_render.server")

# In-memory job tracker
jobs: Dict[str, Dict] = {}


def run_production_job(job_id: str, params: Dict):
    """Background thread: run the production pipeline."""
    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["started_at"] = time.time()

        pipeline = ProductionPipeline(
            width=params.get("width", config.DEFAULT_WIDTH),
            height=params.get("height", config.DEFAULT_HEIGHT),
        )

        result = pipeline.produce(
            channel=params["channel"],
            topic=params["topic"],
            duration_minutes=params.get("duration_minutes", 5),
            num_scenes=params.get("num_scenes", 8),
            upload=params.get("upload", True),
        )

        jobs[job_id]["status"] = "complete"
        jobs[job_id]["result"] = result
        jobs[job_id]["finished_at"] = time.time()

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["finished_at"] = time.time()


class RenderHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the render API."""

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _read_body(self) -> Dict:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        return json.loads(body) if body else {}

    def do_OPTIONS(self):
        """CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/health":
            self._send_json({
                "status": "ok",
                "version": "1.0.0",
                "engine": "spiral_render",
                "active_jobs": sum(1 for j in jobs.values() if j["status"] == "running"),
            })

        elif path.startswith("/status/"):
            job_id = path.split("/status/")[-1]
            if job_id in jobs:
                job = jobs[job_id]
                response = {
                    "job_id": job_id,
                    "status": job["status"],
                    "created_at": job.get("created_at"),
                    "started_at": job.get("started_at"),
                    "finished_at": job.get("finished_at"),
                }
                if job["status"] == "complete":
                    response["result"] = job["result"]
                elif job["status"] == "failed":
                    response["error"] = job.get("error")
                self._send_json(response)
            else:
                self._send_json({"error": "Job not found"}, 404)

        elif path == "/jobs":
            self._send_json({
                "jobs": [
                    {"job_id": jid, "status": j["status"], "channel": j["params"].get("channel")}
                    for jid, j in jobs.items()
                ]
            })

        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/render":
            body = self._read_body()

            # Validate required fields
            if not body.get("channel") or not body.get("topic"):
                self._send_json(
                    {"error": "Missing required fields: channel, topic"}, 400
                )
                return

            # Create job
            job_id = str(uuid.uuid4())[:8]
            jobs[job_id] = {
                "status": "queued",
                "params": body,
                "created_at": time.time(),
            }

            # Start in background thread
            thread = threading.Thread(
                target=run_production_job,
                args=(job_id, body),
                daemon=True,
            )
            thread.start()

            self._send_json({
                "job_id": job_id,
                "status": "queued",
                "message": f"Production started for {body['channel']}: {body['topic']}",
                "status_url": f"/status/{job_id}",
            }, 202)

        elif path == "/render/quick":
            """Synchronous render — blocks until complete. For small jobs."""
            body = self._read_body()

            if not body.get("channel") or not body.get("topic"):
                self._send_json({"error": "Missing: channel, topic"}, 400)
                return

            try:
                pipeline = ProductionPipeline(
                    width=body.get("width", config.DEFAULT_WIDTH),
                    height=body.get("height", config.DEFAULT_HEIGHT),
                )
                result = pipeline.produce(
                    channel=body["channel"],
                    topic=body["topic"],
                    duration_minutes=body.get("duration_minutes", 5),
                    upload=body.get("upload", True),
                )
                self._send_json({"status": "complete", "result": result})
            except Exception as e:
                self._send_json({"status": "failed", "error": str(e)}, 500)

        else:
            self._send_json({"error": "Not found"}, 404)

    def log_message(self, format, *args):
        """Custom log format."""
        logger.info(f"{self.client_address[0]} - {args[0]}")


def start_server(host: str = "0.0.0.0", port: int = 8420):
    """Start the HTTP render server."""
    server = HTTPServer((host, port), RenderHandler)
    logger.info(f"Spiral Render Engine running on http://{host}:{port}")
    logger.info(f"Endpoints:")
    logger.info(f"  POST /render       — Start production (async)")
    logger.info(f"  POST /render/quick — Synchronous render")
    logger.info(f"  GET  /status/:id   — Check job status")
    logger.info(f"  GET  /jobs         — List all jobs")
    logger.info(f"  GET  /health       — Health check")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped.")
        server.server_close()


if __name__ == "__main__":
    start_server()
