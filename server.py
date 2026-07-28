import os
import sys
import json
import logging
import asyncio
from typing import List
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import process_data

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DashboardServer")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DBSURI_DIR = os.path.join(BASE_DIR, "DBSURI")
DASHBOARD_JSON = os.path.join(BASE_DIR, "dashboard_data.json")

os.makedirs(DBSURI_DIR, exist_ok=True)

# Initialize FastAPI App
app = FastAPI(
    title="Dashboard Fertilizantes 2026",
    description="Servidor Local de Carga Manual y Procesamiento de Reportes CSV",
    version="2.0.0",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/api/data")
async def get_dashboard_data():
    """Returns the processed dashboard_data.json."""
    if not os.path.exists(DASHBOARD_JSON):
        raise HTTPException(status_code=404, detail="Archivo dashboard_data.json no encontrado.")
    
    with open(DASHBOARD_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return JSONResponse(content=data)


@app.post("/api/upload-csvs")
async def upload_csv_files(files: List[UploadFile] = File(...)):
    """
    Recibe los archivos CSV subidos manualmente desde teléfono o PC,
    los guarda en DBSURI y ejecuta el procesamiento con process_data.py.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No se seleccionó ningún archivo CSV.")

    logger.info(f"Recibiendo {len(files)} archivos CSV...")

    # Limpiar archivos CSV viejos antes de guardar los nuevos
    for existing in os.listdir(DBSURI_DIR):
        if existing.lower().endswith(".csv"):
            try:
                os.remove(os.path.join(DBSURI_DIR, existing))
            except Exception:
                pass

    # Guardar cada archivo subido
    saved_files = []
    for file in files:
        if not file.filename.lower().endswith(".csv"):
            continue
        
        file_path = os.path.join(DBSURI_DIR, file.filename)
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        saved_files.append(file.filename)
        logger.info(f"Archivo guardado: {file.filename}")

    if not saved_files:
        raise HTTPException(status_code=400, detail="Ninguno de los archivos subidos es un archivo .csv válido.")

    logger.info("Procesando datos con process_data.py...")
    try:
        process_data.process_all_data()
        logger.info("✅ Procesamiento completado exitosamente.")
        return JSONResponse(content={
            "status": "ok",
            "message": f"Se procesaron {len(saved_files)} reportes CSV exitosamente.",
            "saved_files": saved_files
        })
    except Exception as e:
        logger.error(f"Error procesando datos: {e}")
        raise HTTPException(status_code=500, detail=f"Error al procesar datos CSV: {str(e)}")


# ============================================================================
# Static File Serving (Dashboard)
# ============================================================================

@app.get("/")
async def serve_index():
    """Serve index.html."""
    index_path = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return HTMLResponse("<h1>Dashboard no encontrado</h1>", status_code=404)


app.mount("/", StaticFiles(directory=BASE_DIR), name="static")


# ============================================================================
# Entry Point
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    import socket

    def is_port_in_use(p):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', p)) == 0

    port = 8080
    if is_port_in_use(port):
        port = 8085

    print("=" * 60)
    print("  Dashboard Fertilizantes - Servidor de Carga Manual CSV")
    print(f"  Abra su navegador en: http://localhost:{port}")
    print("=" * 60)
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
