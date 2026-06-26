"""FastAPI dashboard server with SSE for real-time log streaming."""
import asyncio
import json
import os
from pathlib import Path

import aiofiles
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="AI Company Dashboard")

WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", "./workspace"))
STATE_DIR = WORKSPACE_DIR / "state"
OUTPUT_DIR = WORKSPACE_DIR / "output"


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return html_path.read_text(encoding="utf-8")


@app.get("/api/state")
async def get_state():
    state_path = STATE_DIR / "project.json"
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text())
    except Exception:
        return {}


@app.get("/api/files")
async def list_output_files():
    files = []
    if OUTPUT_DIR.exists():
        for p in OUTPUT_DIR.rglob("*"):
            if p.is_file():
                files.append(str(p.relative_to(OUTPUT_DIR)))
    return {"files": files}


@app.get("/api/logs/stream")
async def stream_logs():
    """SSE endpoint: streams new lines from task_log.jsonl"""
    async def event_generator():
        log_path = STATE_DIR / "task_log.jsonl"
        last_pos = 0
        while True:
            if log_path.exists():
                async with aiofiles.open(log_path, "r", encoding="utf-8") as f:
                    await f.seek(last_pos)
                    content = await f.read()
                    if content:
                        last_pos += len(content.encode("utf-8"))
                        for line in content.strip().split("\n"):
                            if line.strip():
                                yield f"data: {line}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/logs")
async def get_logs(limit: int = 100):
    log_path = STATE_DIR / "task_log.jsonl"
    if not log_path.exists():
        return {"logs": []}
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    logs = []
    for line in lines[-limit:]:
        try:
            logs.append(json.loads(line))
        except Exception:
            pass
    return {"logs": logs}
