import asyncio
import os
import sys
import json
import logging
import subprocess
from typing import Dict, List, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from suri_downloader import SURIDownloader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Dashboard_Server")

# ============================================================================
# Paths
# ============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DBSURI_DIR = os.path.join(BASE_DIR, "DBSURI")
DASHBOARD_JSON = os.path.join(BASE_DIR, "dashboard_data.json")
PROCESS_SCRIPT = os.path.join(BASE_DIR, "process_data.py")

# ============================================================================
# FastAPI App
# ============================================================================
app = FastAPI(title="Dashboard Fertilizantes - Server", version="1.0")

# SURI Downloader Engine
downloader = SURIDownloader(downloads_dir=DBSURI_DIR, user_data_dir=os.path.join(BASE_DIR, "browser_user_data"))

# SSE event queues for real-time progress
event_queues: List[asyncio.Queue] = []


def broadcast_event(event_data: Dict[str, Any]):
    """Send event to all connected SSE clients."""
    for q in list(event_queues):
        try:
            q.put_nowait(event_data)
        except Exception:
            pass


downloader.set_progress_callback(broadcast_event)


# ============================================================================
# Pydantic Models
# ============================================================================
class LoginRequest(BaseModel):
    usuario: str
    password: str


class UpdateRequest(BaseModel):
    usuario: str
    password: str


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/api/data")
async def get_dashboard_data():
    """Serve the current dashboard_data.json."""
    if not os.path.exists(DASHBOARD_JSON):
        raise HTTPException(status_code=404, detail="dashboard_data.json not found")
    return FileResponse(DASHBOARD_JSON, media_type="application/json")


@app.get("/api/check-session")
async def check_session():
    """Check if there's an active SURI browser session."""
    if not downloader.is_connected:
        return {"active": False, "message": "Navegador no iniciado"}

    has_session = await downloader.check_session()
    return {
        "active": has_session,
        "message": "Sesión activa en SURI" if has_session else "Sin sesión activa"
    }


@app.get("/api/update-status")
async def get_update_status():
    """Get current status of the update process."""
    return {
        "is_running": downloader.is_running,
        "is_connected": downloader.is_connected,
    }


@app.post("/api/update-data")
async def update_data(req: UpdateRequest):
    """
    Trigger the full update pipeline:
    1. Login to SURI
    2. Download 7 CSV reports
    3. Run process_data.py
    4. Reload dashboard
    """
    if downloader.is_running:
        raise HTTPException(status_code=400, detail="Ya hay una actualización en progreso.")

    # Launch the update pipeline as a background task
    asyncio.create_task(_run_full_pipeline(req.usuario, req.password))
    return {"ok": True, "message": "Actualización iniciada."}


@app.post("/api/stop-update")
async def stop_update():
    """Stop the running update process."""
    downloader.request_stop()
    return {"ok": True, "message": "Solicitud de detención enviada."}


@app.get("/api/events")
async def sse_events(request: Request):
    """SSE endpoint for real-time progress events."""
    async def event_generator():
        q = asyncio.Queue()
        event_queues.append(q)
        try:
            # Send initial connected event
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        finally:
            if q in event_queues:
                event_queues.remove(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ============================================================================
# Background Pipeline
# ============================================================================

async def _run_full_pipeline(username: str, password: str):
    """Execute the complete update pipeline in background."""
    try:
        # Phase 1: Download reports from SURI
        broadcast_event({
            "type": "progress",
            "message": "🚀 Iniciando pipeline de actualización...",
            "level": "info",
            "progress": 1,
            "step": "start",
        })

        success = await downloader.download_all_reports(username, password)

        if not success:
            broadcast_event({
                "type": "progress",
                "message": "❌ La descarga de reportes falló. No se actualizarán los datos.",
                "level": "error",
                "progress": 0,
                "step": "error",
            })
            return

        # Phase 2: Process data (run process_data.py)
        broadcast_event({
            "type": "progress",
            "message": "🔄 Procesando datos descargados con process_data.py...",
            "level": "info",
            "progress": 88,
            "step": "processing",
        })

        try:
            process_success = await _run_process_data()
            if not process_success:
                broadcast_event({
                    "type": "progress",
                    "message": "⚠️ Error al procesar los datos.",
                    "level": "error",
                    "progress": 0,
                    "step": "error",
                })
                return
        except Exception as e:
            broadcast_event({
                "type": "progress",
                "message": f"❌ Error en procesamiento: {e}",
                "level": "error",
                "progress": 0,
                "step": "error",
            })
            return

        # Phase 3: Signal completion
        broadcast_event({
            "type": "complete",
            "message": "🎉 ¡Dashboard actualizado exitosamente!",
            "level": "success",
            "progress": 100,
            "step": "complete",
        })

    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        broadcast_event({
            "type": "progress",
            "message": f"💥 Error crítico en el pipeline: {e}",
            "level": "error",
            "progress": 0,
            "step": "error",
        })


async def _run_process_data() -> bool:
    """Run process_data.py as subprocess."""
    try:
        python_exe = sys.executable
        process = await asyncio.create_subprocess_exec(
            python_exe, PROCESS_SCRIPT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=BASE_DIR,
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=600)

        if process.returncode == 0:
            output = stdout.decode("utf-8", errors="replace")
            logger.info(f"process_data.py output: {output[-500:]}")
            broadcast_event({
                "type": "progress",
                "message": "✅ process_data.py ejecutado correctamente.",
                "level": "success",
                "progress": 93,
                "step": "processing",
            })
            return True
        else:
            error_output = stderr.decode("utf-8", errors="replace")
            logger.error(f"process_data.py failed: {error_output[-500:]}")
            broadcast_event({
                "type": "progress",
                "message": f"⚠️ process_data.py error: {error_output[-200:]}",
                "level": "error",
                "progress": 0,
                "step": "error",
            })
            return False
    except asyncio.TimeoutError:
        broadcast_event({
            "type": "progress",
            "message": "⚠️ process_data.py excedió el tiempo límite (10 min).",
            "level": "error",
            "progress": 0,
            "step": "error",
        })
        return False
    except Exception as e:
        logger.error(f"Error running process_data.py: {e}")
        return False


# ============================================================================
# Static File Serving (Dashboard)
# ============================================================================

@app.get("/")
async def serve_index():
    """Serve the dashboard index.html."""
    index_path = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return HTMLResponse("<h1>Dashboard no encontrado</h1>", status_code=404)


# Mount static files (CSS, JS, images, etc.)
# This must be LAST to avoid catching API routes
app.mount("/", StaticFiles(directory=BASE_DIR), name="static")


# ============================================================================
# Entry Point
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  Dashboard Fertilizantes - Servidor Local")
    print("  Abra su navegador en: http://localhost:8080")
    print("=" * 60)
    uvicorn.run("server:app", host="127.0.0.1", port=8080, reload=False)
