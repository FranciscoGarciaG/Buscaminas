import os
import sys
import asyncio
import logging
from suri_downloader import SURIDownloader
import process_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Cloud_Update")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DBSURI_DIR = os.path.join(BASE_DIR, "DBSURI")

async def run_update_pipeline():
    """
    Ejecutor 100% Nube para GitHub Actions.
    Obtiene credenciales desde variables de entorno y ejecuta el pipeline.
    """
    logger.info("=" * 60)
    logger.info("  Iniciando Actualización 100% Nube (SURI -> Process -> Posit Cloud)")
    logger.info("=" * 60)

    username = (
        os.environ.get("INPUT_USUARIO", "").strip() or 
        os.environ.get("SECRET_USUARIO", "").strip() or 
        os.environ.get("SURI_USUARIO", "").strip()
    )
    password = (
        os.environ.get("INPUT_PASSWORD", "").strip() or 
        os.environ.get("SECRET_PASSWORD", "").strip() or 
        os.environ.get("SURI_PASSWORD", "").strip()
    )

    if not username or not password:
        logger.error("❌ Error: Variables de usuario o contraseña SURI no encontradas.")
        sys.exit(1)

    logger.info(f"Usuario SURI detectado: '{username}' | Longitud de Contraseña: {len(password)} caracteres")
    logger.info("Iniciando descargador SURI con Playwright Headless...")

    downloader = SURIDownloader(downloads_dir=DBSURI_DIR, user_data_dir=os.path.join(BASE_DIR, "browser_user_data"))
    
    # Run SURI download pipeline
    success = await downloader.download_all_reports(username, password)
    await downloader.close()

    if not success:
        logger.error("❌ La descarga de reportes de SURI falló.")
        sys.exit(1)

    logger.info("✅ Descarga de 7 reportes CSV completada exitosamente.")
    logger.info("🔄 Procesando datos con process_data.py...")

    # Run data processing
    try:
        process_data.process_all_data()
        logger.info("✅ dashboard_data.json actualizado correctamente.")
    except Exception as e:
        logger.error(f"❌ Error al procesar los datos: {e}")
        sys.exit(1)

    logger.info("🎉 Pipeline completado exitosamente en la nube.")

if __name__ == "__main__":
    asyncio.run(run_update_pipeline())
