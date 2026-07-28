import asyncio
import os
import re
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from playwright.async_api import async_playwright, BrowserContext, Page

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SURI_Downloader")

# ============================================================================
# Configuración de los 7 reportes que alimentan el dashboard
# ============================================================================
REPORTS_CONFIG = [
    # 6 Cortes Nacionales (Componente 1051 - FERTILIZANTES)
    {
        "componente": "1051", 
        "componente_label": "1051 - FERTILIZANTES",
        "entidad": "NACIONAL", 
        "periodicidad": "PRIMER CORTE",  
        "label": "Nacional - Primer Corte"
    },
    {
        "componente": "1051", 
        "componente_label": "1051 - FERTILIZANTES",
        "entidad": "NACIONAL", 
        "periodicidad": "SEGUNDO CORTE", 
        "label": "Nacional - Segundo Corte"
    },
    {
        "componente": "1051", 
        "componente_label": "1051 - FERTILIZANTES",
        "entidad": "NACIONAL", 
        "periodicidad": "TERCER CORTE",  
        "label": "Nacional - Tercer Corte"
    },
    {
        "componente": "1051", 
        "componente_label": "1051 - FERTILIZANTES",
        "entidad": "NACIONAL", 
        "periodicidad": "CUARTO CORTE",  
        "label": "Nacional - Cuarto Corte"
    },
    {
        "componente": "1051", 
        "componente_label": "1051 - FERTILIZANTES",
        "entidad": "NACIONAL", 
        "periodicidad": "QUINTO CORTE",  
        "label": "Nacional - Quinto Corte"
    },
    {
        "componente": "1051", 
        "componente_label": "1051 - FERTILIZANTES",
        "entidad": "NACIONAL", 
        "periodicidad": "SEXTO CORTE",   
        "label": "Nacional - Sexto Corte"
    },
    # 1 Reporte Sinaloa (Componente 1053 - PROYECTO EMERGENTE DE FERTILIZANTES)
    {
        "componente": "1053", 
        "componente_label": "1053 - PROYECTO EMERGENTE DE FERTILIZANTES",
        "entidad": "SINALOA", 
        "periodicidad": "ANUAL", 
        "label": "Sinaloa - Anual"
    },
]

# Filtros fijos que no cambian entre reportes
FIXED_FILTERS = {
    "anio": "2026",
    "programa": "105",
    "programa_label": "105 - PROGRAMA NACIONAL DE FERTILIZANTES",
    "instancia": "130",
    "instancia_label": "130 - REPRESENTACIONES ESTATALES DE LA SADER",
    "tipoReporte": "BENEFICIARIOS MULTIFERTILIZANTES",
}

# URL del módulo de Reportes Operativos SIGAP
REPORTES_URL = "https://surif.agricultura.gob.mx:8036/sigap/reportes-operativos"
LOGIN_URL = "https://www.suri.agricultura.gob.mx/login"
HOME_URL = "https://www.suri.agricultura.gob.mx/home"


class SURIDownloader:
    """
    Módulo simplificado de descarga de reportes SURI para el Dashboard Estadístico.
    Extrae la lógica esencial del SURIEngine de CLOWNSURI:
    - Login con Playwright headless + contexto persistente
    - Detección automática de sesión activa (evita fallos por redirección a HOME)
    - Navegación a Reportes Operativos
    - Selección de filtros en cascada con esperas Livewire y mensajes detallados en tiempo real
    - Descarga secuencial de los 7 reportes CSV
    """

    def __init__(self, downloads_dir: str, user_data_dir: str = "browser_user_data"):
        self.downloads_dir = os.path.abspath(downloads_dir)
        self.user_data_dir = os.path.abspath(user_data_dir)
        os.makedirs(self.downloads_dir, exist_ok=True)
        os.makedirs(self.user_data_dir, exist_ok=True)

        self.playwright = None
        self.browser_context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_connected = False
        self.is_running = False
        self.stop_requested = False

        # Progress callback for SSE
        self.progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None

    def set_progress_callback(self, callback: Callable[[Dict[str, Any]], None]):
        self.progress_callback = callback

    def emit(self, message: str, level: str = "info", progress: int = 0, step: str = ""):
        """Emit progress event to connected clients."""
        logger.info(f"[{level.upper()}] {message}")
        if self.progress_callback:
            event = {
                "type": "progress",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "message": message,
                "level": level,
                "progress": progress,
                "step": step,
            }
            try:
                self.progress_callback(event)
            except Exception as e:
                logger.error(f"Error in progress callback: {e}")

    # =========================================================================
    # Browser Lifecycle
    # =========================================================================

    async def start_browser(self, headless: bool = True) -> bool:
        """Launch persistent Chromium context (keeps cookies/session across runs)."""
        try:
            self.emit("Iniciando navegador Chromium...", "info", 2, "browser")
            self.playwright = await async_playwright().start()
            self.browser_context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=headless,
                accept_downloads=True,
                ignore_https_errors=True,
                viewport={"width": 1440, "height": 900},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--ignore-certificate-errors",
                    "--ignore-ssl-errors",
                    "--allow-insecure-localhost",
                ],
            )
            pages = self.browser_context.pages
            self.page = pages[0] if pages else await self.browser_context.new_page()
            self.is_connected = True
            self.emit("Navegador iniciado correctamente.", "success", 5, "browser")
            return True
        except Exception as e:
            self.emit(f"Error al iniciar navegador: {e}", "error", 0, "browser")
            return False

    async def close(self):
        """Close browser and Playwright."""
        if self.browser_context:
            try:
                await self.browser_context.close()
            except Exception:
                pass
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass
        self.is_connected = False
        self.is_running = False

    # =========================================================================
    # Session & Login Detection
    # =========================================================================

    async def check_session(self) -> bool:
        """Check if there's an active SURI session."""
        if not self.page or self.page.is_closed():
            return False
        try:
            url = self.page.url
            if not url or url == "about:blank":
                await self.page.goto(HOME_URL, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                url = self.page.url
            return "login" not in url and ("home" in url or "suri" in url or "sigap" in url or "reportes" in url)
        except Exception:
            return False

    async def auto_login(self, username: str, password: str) -> bool:
        """Login to SURI portal with smart session detection (handles auto-redirects to HOME)."""
        if not self.page:
            self.emit("Navegador no iniciado.", "error", 0, "login")
            return False

        try:
            self.emit("Navegando a la página de login del SURI...", "info", 8, "login")
            
            current_url = self.page.url
            if "login" not in current_url and ("home" in current_url or "sigap" in current_url or "reportes" in current_url):
                self.emit("✅ Sesión activa detectada en SURI (no requiere inicio de sesión).", "success", 15, "login")
                return True

            await self.page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(2.5)

            url_after_goto = self.page.url
            if "login" not in url_after_goto or "home" in url_after_goto or "sigap" in url_after_goto or "reportes" in url_after_goto:
                self.emit("✅ Sesión activa detectada (redirigido automáticamente a inicio).", "success", 15, "login")
                return True

            self.emit("Ingresando credenciales de acceso...", "info", 10, "login")
            try:
                user_input = await self.page.wait_for_selector(
                    "#ln_usuario, input[name='ln_usuario'], input[name='usuario'], input[type='text']",
                    state="attached",
                    timeout=10000,
                )
            except Exception:
                if "login" not in self.page.url:
                    self.emit("✅ Redirigido exitosamente a SURI.", "success", 15, "login")
                    return True
                raise Exception("No se encontró el campo de usuario en la página de login.")

            if user_input:
                await user_input.focus()
                await user_input.fill("")
                await user_input.type(username, delay=30)
                self.emit(f"Usuario '{username}' ingresado.", "info", 11, "login")

            pass_input = await self.page.query_selector(
                "#ln_password, input[name='ln_password'], input[name='password'], input[type='password']"
            )
            if pass_input:
                await pass_input.focus()
                await pass_input.fill("")
                await pass_input.type(password, delay=30)
                self.emit("Contraseña ingresada.", "info", 12, "login")

            self.emit("Enviando formulario de login...", "info", 13, "login")
            
            # Submit via Enter key on password input first
            if pass_input:
                await pass_input.press("Enter")
                await asyncio.sleep(2)

            # Check if SURI popped up #modalErrors (e.g. invalid credentials or session alert)
            modal_err = await self.page.query_selector("#modalErrors, .modal-danger, .modal.in")
            if modal_err:
                try:
                    modal_text = await modal_err.inner_text()
                    clean_text = " ".join(modal_text.split())
                    self.emit(f"⚠️ Alerta SURI (#modalErrors): '{clean_text}'", "warning", 0, "login")
                    
                    # Dismiss modal so it doesn't block the screen
                    ok_btn = await modal_err.query_selector("button, input[type='button'], a.btn")
                    if ok_btn:
                        await ok_btn.click(force=True)
                        await asyncio.sleep(2)
                except Exception as me:
                    logger.warning(f"Error handling modalErrors: {me}")

            # Fallback submit button click if still on login page and modal is gone
            if "login" in self.page.url:
                submit_btn = await self.page.query_selector(
                    "form#formLogin input[type='submit'], #formLogin input.btn-success, "
                    "input[type='submit'], button[type='submit'], #btn_login"
                )
                if submit_btn and await submit_btn.is_visible():
                    try:
                        await submit_btn.click(timeout=5000)
                    except Exception:
                        pass

            try:
                await self.page.wait_for_url(lambda u: "login" not in u or "home" in u or "sigap" in u or "reportes" in u, timeout=12000)
            except Exception:
                pass

            await asyncio.sleep(3)

            url_after = self.page.url
            if "login" not in url_after or "home" in url_after or "sigap" in url_after or "reportes" in url_after:
                self.emit("✅ Inicio de sesión exitoso.", "success", 15, "login")
                return True
            else:
                # Capture page error message for precise diagnosis
                error_msg = ""
                try:
                    err_elem = await self.page.query_selector("#modalErrors, .alert, .alert-danger, .error, .help-block, #msg_error")
                    if err_elem:
                        error_msg = await err_elem.inner_text()
                except Exception:
                    pass

                if error_msg:
                    clean_err = " ".join(error_msg.split())
                    self.emit(f"⚠️ Mensaje devuelto por SURI: '{clean_err}'", "warning", 0, "login")
                else:
                    self.emit(f"⚠️ No se pudo verificar el login (URL actual: {url_after}). Revise credenciales SURI_PASSWORD en GitHub Secrets.", "warning", 0, "login")
                return False
        except Exception as e:
            self.emit(f"❌ Error en login: {e}", "error", 0, "login")
            return False

    # =========================================================================
    # SURI Navigation & Filter Helpers
    # =========================================================================

    async def wait_for_livewire_idle(self, timeout_ms: int = 15000) -> bool:
        """Wait for Livewire/AJAX spinners and modals to finish."""
        if not self.page:
            return False

        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) * 1000 < timeout_ms:
            if self.stop_requested:
                return False
            try:
                busy = await self.page.evaluate("""() => {
                    const loadingModal = document.getElementById('loadingModal');
                    if (loadingModal && loadingModal.classList.contains('show')) return true;
                    const spinners = document.querySelectorAll('.spinner-border');
                    for (const sp of spinners) {
                        if (sp.offsetWidth > 0 && sp.offsetHeight > 0) return true;
                    }
                    return false;
                }""")
                if not busy:
                    await asyncio.sleep(0.4)
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.3)
        return False

    async def dismiss_modals(self) -> bool:
        """Dismiss active SURI popup/modal dialogs."""
        if not self.page:
            return False
        try:
            return await self.page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button, a.btn, input[type="button"]'));
                const match = btns.find(b => {
                    const txt = b.innerText ? b.innerText.trim().toLowerCase() : '';
                    return vis = b.offsetWidth > 0 && b.offsetHeight > 0;
                    return vis && (txt === 'aceptar' || txt === 'entendido' || txt === 'continuar' || txt === 'cerrar');
                });
                if (match) { match.click(); return true; }
                return false;
            }""")
        except Exception:
            return False

    async def is_server_error_500(self) -> bool:
        """Check if SURI returned a 500 error."""
        if not self.page:
            return False
        try:
            body_text = await self.page.inner_text("body")
            return body_text.strip().startswith("{") and '"code":500' in body_text
        except Exception:
            return False

    async def _find_and_click_link(self, module_name: str, target_url: str) -> bool:
        """Find and click a link element by innerText or href on SURI DOM (prevents 'Acceso Denegado')."""
        try:
            clean_path = target_url
            for domain in [
                "https://www.suri.agricultura.gob.mx",
                "https://surif.agricultura.gob.mx:8036",
                "https://surif.agricultura.gob.mx:8037",
                "https://www.suri.agricultura.gob.mx:8003",
                "https://www.suri.agricultura.gob.mx:8004",
                "https://www.suri.agricultura.gob.mx:8005",
            ]:
                clean_path = clean_path.replace(domain, "")

            return await self.page.evaluate("""({ modName, relPath }) => {
                const links = Array.from(document.querySelectorAll('a, button, input[type="button"], div.well a'));

                let target = links.find(l => {
                    const txt = l.innerText ? l.innerText.trim().toLowerCase() : '';
                    return txt && (txt === modName.toLowerCase() || txt.includes(modName.toLowerCase()));
                });

                if (!target && relPath && relPath !== '/') {
                    target = links.find(l => {
                        const href = l.getAttribute('href') || '';
                        return href && (href.includes(relPath) || relPath.includes(href));
                    });
                }

                if (target) {
                    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    target.click();
                    return true;
                }
                return false;
            }""", {"modName": module_name, "relPath": clean_path})
        except Exception:
            return False

    async def _click_tab(self, tab_name: str) -> bool:
        """Click a top-level SURI tab (e.g. SIGAP, SURI, REPORTES)."""
        if not self.page:
            return False
        try:
            self.emit(f"Haciendo clic en pestaña '{tab_name}'...", "info", 0, "navigate")
            await self.page.evaluate("""(tabText) => {
                const els = Array.from(document.querySelectorAll('a, button, li, div.well'));
                const match = els.find(e => e.innerText && e.innerText.trim().toUpperCase().includes(tabText.toUpperCase()) && e.offsetWidth > 0);
                if (match) match.click();
            }""", tab_name)
            await asyncio.sleep(2)
            return True
        except Exception:
            return False

    async def navigate_to_reportes(self) -> bool:
        """Navigate to Reportes Operativos page using click-based navigation to avoid 'Acceso Denegado'."""
        if not self.page:
            return False

        try:
            self.emit("Navegando a Reportes Operativos (vía menú SURI)...", "info", 18, "navigate")

            current_url = self.page.url

            if "reportes" in current_url and "acceso_denegado" not in current_url:
                self.emit("✅ Ya en página de Reportes Operativos.", "success", 20, "navigate")
                return True

            if "home" not in current_url:
                self.emit("Regresando al Panel de Control...", "info", 18, "navigate")
                await self.page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

            await self._click_tab("SIGAP")
            await asyncio.sleep(2)

            clicked = await self._find_and_click_link("Reporte Operativo", REPORTES_URL)
            if not clicked:
                clicked = await self._find_and_click_link("Reportes", REPORTES_URL)
            if not clicked:
                clicked = await self._find_and_click_link("reportes-operativos", REPORTES_URL)

            if clicked:
                self.emit("Clic realizado, esperando carga de página...", "info", 19, "navigate")
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=30000)
                except Exception:
                    pass
                await asyncio.sleep(3)
                await self.wait_for_livewire_idle()
            else:
                self.emit("⚠️ No se encontró enlace, intentando acceso directo...", "warning", 19, "navigate")
                await self.page.goto(REPORTES_URL, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(3)
                await self.wait_for_livewire_idle()

            url = self.page.url
            if "acceso_denegado" in url:
                self.emit("⚠️ Acceso denegado. Reintentando desde home...", "warning", 18, "navigate")
                await self.page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(4)
                await self._click_tab("SIGAP")
                await asyncio.sleep(3)
                await self._find_and_click_link("Reporte Operativo", REPORTES_URL)
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=30000)
                except Exception:
                    pass
                await asyncio.sleep(4)
                await self.wait_for_livewire_idle()
                url = self.page.url

            if "reportes" in url and "acceso_denegado" not in url:
                self.emit("✅ En página de Reportes Operativos.", "success", 20, "navigate")
                return True

            if "login" in url:
                self.emit("⚠️ Sesión expirada, necesita login.", "warning", 0, "navigate")
                return False

            if "acceso_denegado" in url:
                self.emit("❌ Acceso denegado persistente. El SURI bloqueó el acceso.", "error", 0, "navigate")
                return False

            self.emit(f"Navegación completada a: {url}", "info", 20, "navigate")
            return True
        except Exception as e:
            self.emit(f"Error navegando a reportes: {e}", "error", 0, "navigate")
            return False

    async def select_filter(self, select_id: str, value: str, label: str = "", filter_name: str = "") -> bool:
        """Select a value in a SURI <select> element, trigger Livewire cascade, and emit progress event."""
        if not self.page or not value:
            return False

        display = label or value
        field_title = filter_name or select_id
        try:
            selected_text = display

            # Try selection by label, value, or JS option text search
            try:
                await self.page.select_option(f"#{select_id}", label=value)
            except Exception:
                try:
                    await self.page.select_option(f"#{select_id}", value=value)
                except Exception:
                    res = await self.page.evaluate("""({ selectId, val }) => {
                        let el = document.getElementById(selectId) || document.querySelector(`select[name="${selectId}"]`);
                        if (!el) return { success: false };
                        
                        const options = Array.from(el.options);
                        const match = options.find(o => {
                            const t = o.text ? o.text.trim().toUpperCase() : '';
                            return t === val.toUpperCase() || t.includes(val.toUpperCase());
                        });
                        
                        if (match) {
                            el.value = match.value;
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            return { success: true, text: match.text ? match.text.trim() : val };
                        }
                        return { success: false };
                    }""", {"selectId": select_id, "val": value})
                    if res and res.get("text"):
                        selected_text = res.get("text")

            # Emit real-time log event for this filter selection
            self.emit(f"  ↳ {field_title}: {selected_text}", "info")

            await self.wait_for_livewire_idle(15000)
            await asyncio.sleep(0.5)
            return True
        except Exception as e:
            self.emit(f"⚠️ Error seleccionando {field_title} = {display}: {e}", "warning")
            return False

    async def click_generate_report(self, timeout_ms: int = 180000) -> Optional[str]:
        """Click 'Generar reporte' button and capture the downloaded file."""
        if not self.page:
            return None

        try:
            if await self.is_server_error_500():
                raise Exception("Error 500 en servidor SURI")

            await self.dismiss_modals()

            btn_info = await self.page.evaluate("""() => {
                const knownIds = ['btnGenerarReporte', 'btnConsulta'];
                for (const id of knownIds) {
                    const el = document.getElementById(id);
                    if (el && el.offsetWidth > 0) return { found: true, id: id };
                }
                const buttons = Array.from(document.querySelectorAll('a.btn-success, button.btn-success'));
                const match = buttons.find(b => {
                    const txt = b.innerText ? b.innerText.trim().toLowerCase() : '';
                    return (txt.includes('generar') || txt.includes('buscar')) && b.offsetWidth > 0;
                });
                if (match) return { found: true, id: match.id || '' };
                return { found: false };
            }""")

            if not btn_info or not btn_info.get("found"):
                raise Exception("No se encontró el botón verde 'Generar reporte'")

            btn_id = btn_info.get("id", "")
            self.emit("🔍 Haciendo clic en 'Generar reporte' (esperando descarga del CSV...)", "info")

            download = None
            try:
                async with self.page.expect_download(timeout=timeout_ms) as download_info:
                    await self.page.evaluate("""(btnId) => {
                        let btn = btnId ? document.getElementById(btnId) : null;
                        if (!btn) {
                            const buttons = Array.from(document.querySelectorAll('a.btn-success, button.btn-success'));
                            btn = buttons.find(b => b.offsetWidth > 0);
                        }
                        if (btn) btn.click();
                    }""", btn_id)

                    start = asyncio.get_event_loop().time()
                    while (asyncio.get_event_loop().time() - start) < (timeout_ms / 1000):
                        if self.stop_requested:
                            break
                        if await self.is_server_error_500():
                            raise Exception("Error 500 durante generación del reporte")
                        await self.dismiss_modals()
                        await asyncio.sleep(1)

                download = await download_info.value
            except Exception as e:
                if "stop" in str(e).lower() or self.stop_requested:
                    return None
                raise

            if not download:
                return None

            original_name = download.suggested_filename
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            clean_name = f"Reporte_SURI_{timestamp_str}_{original_name}"
            target_path = os.path.join(self.downloads_dir, clean_name)
            await download.save_as(target_path)

            if not os.path.exists(target_path) or os.path.getsize(target_path) < 100:
                if os.path.exists(target_path):
                    os.remove(target_path)
                self.emit("⚠️ El archivo descargado está vacío.", "warning")
                return None

            size_mb = os.path.getsize(target_path) / (1024 * 1024)
            self.emit(f"✅ Descargado ({size_mb:.1f} MB): {clean_name}", "success")
            return target_path

        except Exception as e:
            self.emit(f"❌ Error en descarga: {e}", "error")
            return None

    # =========================================================================
    # Main Pipeline: Download All 7 Reports
    # =========================================================================

    async def download_all_reports(self, username: str, password: str) -> bool:
        """
        Complete pipeline: login → navigate → download 7 reports sequentially.
        Returns True if all reports downloaded successfully.
        """
        self.is_running = True
        self.stop_requested = False
        total_reports = len(REPORTS_CONFIG)
        completed = 0
        failed = 0

        try:
            # Step 1: Start browser
            if not self.is_connected:
                if not await self.start_browser(headless=True):
                    self.emit("❌ No se pudo iniciar el navegador.", "error", 0, "error")
                    return False

            # Step 2: Login (or verify existing active session)
            has_session = await self.check_session()
            if not has_session:
                self.emit("Verificando inicio de sesión en SURI...", "info", 7, "login")
                if not await self.auto_login(username, password):
                    self.emit("❌ Fallo en el inicio de sesión.", "error", 0, "error")
                    return False
            else:
                self.emit("✅ Sesión activa detectada en SURI.", "success", 15, "login")

            # Step 3: Clean old CSVs from DBSURI
            self.emit("Limpiando reportes anteriores en carpeta DBSURI...", "info", 16, "clean")
            old_files = [f for f in os.listdir(self.downloads_dir) if f.lower().endswith(".csv")]
            for f in old_files:
                try:
                    os.remove(os.path.join(self.downloads_dir, f))
                except Exception:
                    pass
            self.emit(f"Se limpiaron {len(old_files)} archivos CSV anteriores.", "info", 17, "clean")

            # Step 4: Navigate to Reportes Operativos
            if not await self.navigate_to_reportes():
                self.emit("❌ No se pudo acceder a Reportes Operativos.", "error", 0, "error")
                return False

            # Step 5: Download each report step-by-step
            for idx, report_cfg in enumerate(REPORTS_CONFIG):
                if self.stop_requested:
                    self.emit("⛔ Proceso detenido por el usuario.", "warning", 0, "stopped")
                    break

                report_label = report_cfg["label"]
                base_progress = 20 + int((idx / total_reports) * 65)
                self.emit(
                    f"📥 Preparando Reporte {idx + 1}/{total_reports}: {report_label}",
                    "info", base_progress, "download"
                )

                success = await self._download_single_report(report_cfg, base_progress)
                if success:
                    completed += 1
                    self.emit(
                        f"✅ Reporte {idx + 1}/{total_reports} completado exitosamente: {report_label}",
                        "success",
                        base_progress + int(65 / total_reports),
                        "download"
                    )
                else:
                    failed += 1
                    self.emit(
                        f"⚠️ Falló la descarga del Reporte {idx + 1}/{total_reports}: {report_label}",
                        "warning", base_progress, "download"
                    )

                if idx < total_reports - 1 and not self.stop_requested:
                    self.emit("Regresando al menú de filtros...", "info", base_progress, "navigate")
                    await self.navigate_to_reportes()
                    await asyncio.sleep(2)

            self.emit(
                f"📊 Descarga finalizada: {completed}/{total_reports} reportes exitosos, {failed} fallidos.",
                "success" if failed == 0 else "warning",
                85, "download_complete"
            )
            return completed > 0

        except Exception as e:
            self.emit(f"💥 Error crítico: {e}", "error", 0, "error")
            return False
        finally:
            self.is_running = False

    async def _download_single_report(self, config: Dict[str, str], base_progress: int) -> bool:
        """Download a single report by selecting each filter step-by-step and emitting real-time progress messages."""
        max_retries = 2

        for attempt in range(max_retries + 1):
            if self.stop_requested:
                return False

            try:
                if attempt > 0:
                    self.emit(f"🔄 Reintentando selección de filtros ({attempt + 1}/{max_retries + 1})...", "warning")
                    await self.navigate_to_reportes()
                    await asyncio.sleep(2)

                # 1. Filtro General: Año
                await self.select_filter("anio", FIXED_FILTERS["anio"], "2026", "Año")
                await asyncio.sleep(1.2)

                # 2. Filtro General: Programa
                await self.select_filter("programa", FIXED_FILTERS["programa"], FIXED_FILTERS["programa_label"], "Programa")
                await asyncio.sleep(1.2)

                # 3. Filtro General: Componente (1051 FERTILIZANTES o 1053 PROYECTO EMERGENTE)
                comp_label = config.get("componente_label", f"Componente {config['componente']}")
                await self.select_filter("componente", config["componente"], comp_label, "Componente")
                await asyncio.sleep(1.2)

                # 4. Filtro General: Instancia Ejecutora
                await self.select_filter("instancia", FIXED_FILTERS["instancia"], FIXED_FILTERS["instancia_label"], "Instancia Ejecutora")
                await asyncio.sleep(1.2)

                # 5. Filtro Particular: Tipo de Reporte
                await self.select_filter("tipoReporte", FIXED_FILTERS["tipoReporte"], "BENEFICIARIOS MULTIFERTILIZANTES", "Tipo de Reporte")
                await asyncio.sleep(1.2)

                # 6. Filtro Particular: Entidad Federativa (NACIONAL o SINALOA)
                await self.select_filter("entidadFederativa", config["entidad"], config["entidad"], "Entidad Federativa")
                await asyncio.sleep(1.2)

                # 7. Filtro Particular: Periodicidad (PRIMER CORTE, ..., SEXTO CORTE, ANUAL)
                await self.select_filter("periodicidad", config["periodicidad"], config["periodicidad"], "Periodicidad")
                await asyncio.sleep(2.0)

                # 8. Filtro Particular: Reporte Específico (Generado por Livewire)
                await self.wait_for_livewire_idle(10000)
                reporte_res = await self.page.evaluate("""() => {
                    const el = document.getElementById('reporte');
                    if (!el) return { success: false };
                    const opts = Array.from(el.options).filter(o => o.value && o.value !== '');
                    if (opts.length > 0) {
                        el.value = opts[0].value;
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        return { success: true, text: opts[0].text ? opts[0].text.trim() : opts[0].value };
                    }
                    return { success: false };
                }""")

                if reporte_res and reporte_res.get("success"):
                    self.emit(f"  ↳ Reporte generado: {reporte_res.get('text')}", "info")
                else:
                    self.emit("  ↳ Generando reporte final en selector...", "info")

                await self.wait_for_livewire_idle(5000)
                await asyncio.sleep(1)

                # Clic en botón verde "Generar reporte"
                file_path = await self.click_generate_report(timeout_ms=180000)
                if file_path:
                    return True

            except Exception as e:
                self.emit(f"⚠️ Error en intento {attempt + 1}: {e}", "warning")
                await asyncio.sleep(3)

        return False

    def request_stop(self):
        """Request to stop the download process."""
        self.stop_requested = True
        self.is_running = False
        self.emit("⛔ Solicitud de detención enviada.", "warning", 0, "stopped")
