import os
import sys
import json
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_JSON = os.path.join(BASE_DIR, "dashboard_data.json")

POSIT_CONNECT_URL = "https://connect.posit.cloud/franciscogarciag"

def sync_to_posit():
    """
    Sincronizador automático de 1 Clic para Posit Cloud / Posit Connect.
    Publica o actualiza el contenido del dashboard en la nube.
    """
    print("=" * 60)
    print("  Sincronizador Automático a Posit Cloud / Connect")
    print(f"  Destino: {POSIT_CONNECT_URL}")
    print("=" * 60)

    if not os.path.exists(DASHBOARD_JSON):
        print("❌ Error: No se encontró dashboard_data.json en el directorio.")
        return False

    print("✅ dashboard_data.json verificado.")
    print("🚀 Sincronizando con Posit Cloud...")

    try:
        # Check if rsconnect CLI is installed
        python_exe = sys.executable
        cmd = [
            python_exe, "-m", "rsconnect", "deploy", "html",
            "--server", POSIT_CONNECT_URL,
            "--entrypoint", "index.html",
            BASE_DIR
        ]
        
        print("Ejecutando despliegue en Posit Connect...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print("\n🎉 ¡Sincronización completada exitosamente!")
            print(f"Tu dashboard actualizado está disponible en: {POSIT_CONNECT_URL}\n")
            return True
        else:
            print("\nℹ️ Para primera autenticación con Posit Publisher:")
            print("1. Abre la extensión 'Posit Publisher' en tu IDE (VS Code).")
            print("2. Selecciona 'Publish Content' -> 'Static Web Site' o 'Python FastAPI'.")
            print("3. Selecciona tu servidor Posit Cloud.")
            print(f"\nDetalles del sistema: {result.stderr[:300]}")
            return False

    except Exception as e:
        print(f"⚠️ Nota de sincronización: {e}")
        return False

if __name__ == "__main__":
    sync_to_posit()
