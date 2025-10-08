import flet as ft
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import threading
import time
import os
import platform
import requests
import shutil
import subprocess
import zipfile
import tarfile
from pathlib import Path

# --- LÓGICA DE BACKEND ---
ESPELHAMENTO_ATIVO = False
class ADBManager:
    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.adb_dir = self.base_dir / "adb"
        self.platform_dir = self.adb_dir / self._get_platform_name()
        self.adb_path = self._get_adb_path()
        self.scrcpy_path = self._get_scrcpy_path()
        self.scrcpy_server_path = self.platform_dir / "scrcpy-server"

    def _get_platform_name(self):
        system = platform.system().lower()
        arch = platform.machine().lower()
        if system == "linux":
            return "linux64" if "64" in arch or "x86_64" in arch else "linux32"
        elif system == "windows":
            return "windows"
        elif system == "darwin":
            return "darwin"
        else:
            return "linux64"

    def _get_adb_path(self):
        return self.platform_dir / ("adb.exe" if platform.system().lower() == "windows" else "adb")

    def _get_scrcpy_path(self):
        exe = "scrcpy.exe" if platform.system().lower() == "windows" else "scrcpy"
        return self.platform_dir / exe

    def download_adb(self):
        if self.adb_path.exists():
            return True, None
        print("Baixando ADB...")
        self.platform_dir.mkdir(parents=True, exist_ok=True)
        urls = {
            "linux64": "https://dl.google.com/android/repository/platform-tools-latest-linux.zip",
            "windows": "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
            "darwin": "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip"
        }
        url = urls.get(self._get_platform_name(), urls["linux64"])
        try:
            zip_path = self.base_dir / "platform-tools.zip"
            with requests.get(url, stream=True) as r, open(zip_path, 'wb') as f:
                shutil.copyfileobj(r.raw, f)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.base_dir)
            extracted_dir = self.base_dir / "platform-tools"
            if extracted_dir.exists():
                for item in extracted_dir.iterdir():
                    if item.name.startswith("adb") or item.name.endswith(".dll"):
                        shutil.move(str(item), str(self.platform_dir / item.name))
                shutil.rmtree(extracted_dir)
            zip_path.unlink()
            if platform.system().lower() != "windows":
                os.chmod(self.adb_path, 0o755)
            return True, None
        except Exception as e:
            error_message = f"Erro ao baixar/extrair ADB: {e}"
            print(error_message)
            return False, error_message

    def download_scrcpy(self):
        if self.scrcpy_path.exists() and self.scrcpy_server_path.exists():
            return True, None
            
        print("Baixando scrcpy...")
        self.platform_dir.mkdir(parents=True, exist_ok=True)

        urls = {
            "linux64": "https://github.com/Genymobile/scrcpy/releases/download/v3.3.3/scrcpy-linux-x86_64-v3.3.3.tar.gz",
            "windows": "https://github.com/Genymobile/scrcpy/releases/download/v3.3.3/scrcpy-win64-v3.3.3.zip",
            "darwin": "https://github.com/Genymobile/scrcpy/releases/download/v3.3.3/scrcpy-macos-x86_64-v3.3.3.tar.gz"
        }
        url = urls.get(self._get_platform_name())
        if not url:
            return False, "Plataforma não suportada para scrcpy"

        try:
            # salvar com o nome certo (mantendo a extensão)
            archive_path = self.base_dir / Path(url).name
            with requests.get(url, stream=True) as r, open(archive_path, 'wb') as f:
                shutil.copyfileobj(r.raw, f)

            extracted_dir = self.base_dir / "scrcpy_extracted"
            if extracted_dir.exists():
                shutil.rmtree(extracted_dir)
            extracted_dir.mkdir(exist_ok=True)

            # extrair dependendo do formato
            if archive_path.suffix == ".zip":
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(extracted_dir)
            elif archive_path.suffixes[-2:] == [".tar", ".gz"]:
                with tarfile.open(archive_path, "r:gz") as tar_ref:
                    tar_ref.extractall(extracted_dir)
            else:
                return False, f"Formato de arquivo não suportado: {archive_path}"

            # procurar executável scrcpy e scrcpy-server
            scrcpy_bin = None
            scrcpy_server = None
            
            for root, dirs, files in os.walk(extracted_dir):
                for fname in files:
                    if fname == ("scrcpy.exe" if platform.system().lower() == "windows" else "scrcpy"):
                        scrcpy_bin = Path(root) / fname
                    elif fname == "scrcpy-server":
                        scrcpy_server = Path(root) / fname

            if not scrcpy_bin or not scrcpy_bin.exists():
                return False, "Executável scrcpy não encontrado no pacote extraído"

            if not scrcpy_server or not scrcpy_server.exists():
                return False, "Arquivo scrcpy-server não encontrado no pacote extraído"

            # mover ambos os arquivos para a pasta da plataforma
            shutil.move(str(scrcpy_bin), str(self.scrcpy_path))
            shutil.move(str(scrcpy_server), str(self.scrcpy_server_path))

            shutil.rmtree(extracted_dir)
            archive_path.unlink()

            if platform.system().lower() != "windows":
                os.chmod(self.scrcpy_path, 0o755)
                os.chmod(self.scrcpy_server_path, 0o755)

            return True, None
        except Exception as e:
            error_message = f"Erro ao baixar/extrair scrcpy: {e}"
            print(error_message)
            return False, error_message

    def get_tools(self):
        # garante que adb e scrcpy existem
        adb_ok, adb_err = self.download_adb()
        scrcpy_ok, scrcpy_err = self.download_scrcpy()

        if not adb_ok:
            return None, adb_err
        if not scrcpy_ok:
            return None, scrcpy_err

        return {
            "adb": str(self.adb_path),
            "scrcpy": str(self.scrcpy_path),
            "scrcpy_server": str(self.scrcpy_server_path)
        }, None


def localizar_adb():
    adb_manager = ADBManager()
    tools, error = adb_manager.get_tools()
    if tools and tools.get("adb"):
        return tools["adb"], None

    try:
        caminho = subprocess.check_output(["which", "adb"], text=True).strip()
        if os.path.exists(caminho):
            return caminho, None
    except Exception:
        for path in ["/usr/bin/adb", "/usr/local/bin/adb", os.path.expanduser("~/.local/bin/adb")]:
            if os.path.exists(path):
                return path, None

    return None, error or "ADB não encontrado no sistema e o download automático falhou."

class AppManager:
    def __init__(self, adb_path):
        self.adb_path = adb_path
        self.icon_cache_dir = Path(__file__).parent / "icon_cache"
        self.icon_cache_dir.mkdir(exist_ok=True)
        self.memory_cache = {}
        self.default_icon_b64 = self._get_default_icon()

    def get_app_icon(self, package_name):
        if package_name in self.memory_cache: return self.memory_cache[package_name]
        cache_file = self.icon_cache_dir / f"{package_name}.png"
        if cache_file.exists():
            try:
                with open(cache_file, "rb") as f: icon_data = base64.b64encode(f.read()).decode()
                icon_url = f"data:image/png;base64,{icon_data}"
                self.memory_cache[package_name] = icon_url
                return icon_url
            except Exception as e: print(f"Erro ao ler cache do ícone: {e}")
        
        icon_bytes = self._extract_icon_from_apk(package_name)

        if icon_bytes:
            try:
                with open(cache_file, "wb") as f: f.write(icon_bytes)
                icon_data = base64.b64encode(icon_bytes).decode()
                icon_url = f"data:image/png;base64,{icon_data}"
                self.memory_cache[package_name] = icon_url
                return icon_url
            except Exception as e: print(f"Erro ao salvar/converter ícone: {e}")
        
        return self.default_icon_b64


    def _extract_icon_from_apk(self, package_name):
        temp_apk_path = None
        try:
            cmd_path = [self.adb_path, "shell", "pm", "path", package_name]
            result = subprocess.run(cmd_path, capture_output=True, text=True, timeout=10)
            if result.returncode != 0 or not result.stdout.strip(): return None
            
            apk_path_on_device = result.stdout.strip().replace("package:", "")
            temp_apk_path = self.icon_cache_dir / f"{package_name}_temp.apk"
            cmd_pull = [self.adb_path, "pull", apk_path_on_device, str(temp_apk_path)]
            subprocess.run(cmd_pull, capture_output=True, timeout=60)

            if not temp_apk_path.exists(): return None

            with zipfile.ZipFile(temp_apk_path, 'r') as apk:
                filenames = apk.namelist()
                search_priority = ['res/mipmap-xxxhdpi-v4/ic_launcher.png', 'res/mipmap-xxhdpi-v4/ic_launcher.png','res/mipmap-xhdpi-v4/ic_launcher.png', 'res/mipmap-hdpi-v4/ic_launcher.png','res/mipmap-mdpi-v4/ic_launcher.png', 'res/mipmap-xxxhdpi/ic_launcher.png','res/mipmap-xxhdpi/ic_launcher.png', 'res/mipmap-xhdpi/ic_launcher.png','res/mipmap-hdpi/ic_launcher.png', 'res/mipmap-mdpi/ic_launcher.png','res/drawable-xxhdpi-v4/icon.png', 'res/drawable-xxhdpi/icon.png',]
                for path in search_priority:
                    if path in filenames:
                        with apk.open(path) as icon_file: return icon_file.read()
                
                possible_icons = [f for f in filenames if 'ic_launcher.png' in f]
                if possible_icons:
                    sorted_icons = sorted(possible_icons, key=lambda p: ('xxxhdpi' in p, 'xxhdpi' in p, 'xhdpi' in p), reverse=True)
                    with apk.open(sorted_icons[0]) as icon_file: return icon_file.read()
            return None
        except Exception as e:
            print(f"Falha ao extrair ícone para {package_name}: {e}")
            return None
        finally:
            if temp_apk_path and temp_apk_path.exists(): temp_apk_path.unlink()

    def _get_default_icon(self):
        default_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="feather feather-box"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>"""
        return f"data:image/svg+xml;base64,{base64.b64encode(default_svg.encode()).decode()}"

    def get_app_info_batch_no_icons(self, package_names):
        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_package = {executor.submit(self.get_single_app_info_no_icon, pkg): pkg for pkg in package_names}
            for future in as_completed(future_to_package):
                try:
                    result = future.result()
                    if result: results.append(result)
                except Exception as e:
                    pkg = future_to_package[future]; print(f"Erro no future para {pkg}: {e}"); results.append({"name": pkg, "package": pkg, "version": "N/A"})
        return results

    def get_single_app_info_no_icon(self, package_name):
        app_name = package_name
        version = "N/A"
        try:
            dump_output = subprocess.check_output([self.adb_path, "shell", "pm", "dump", package_name], text=True, stderr=subprocess.DEVNULL, errors="ignore", timeout=10)
            label_re = re.compile(r"label=(.+)")
            for line in dump_output.splitlines():
                match = label_re.search(line)
                if match:
                    found_name = match.group(1).strip()
                    if found_name and found_name != "null":
                        app_name = found_name
                        break
            dumpsys_output = subprocess.check_output([self.adb_path, "shell", "dumpsys", "package", package_name], text=True, stderr=subprocess.DEVNULL, errors="ignore", timeout=10)
            version_re = re.compile(r"versionName=(.+)")
            for line in dumpsys_output.splitlines():
                match = version_re.search(line)
                if match:
                    version = match.group(1).strip()
                    break
        except Exception: pass
        return {"name": app_name, "package": package_name, "version": version}

class ConfigManager:
    def __init__(self, adb_path): self.adb_path = adb_path
    def _run_adb_command(self, command, timeout=10):
        try:
            result = subprocess.run([self.adb_path, "shell"] + command, capture_output=True, text=True, timeout=timeout, errors='ignore')
            if result.returncode != 0: print(f"Erro no comando 'adb shell {' '.join(command)}': {result.stderr.strip()}"); return None
            return result.stdout.strip()
        except Exception as e: print(f"Exceção ao executar comando: {e}"); return None
    def get_current_display_settings(self):
        size_output = self._run_adb_command(["wm", "size"]); resolution = size_output.replace("Physical size: ", "") if size_output else "N/A"
        density_output = self._run_adb_command(["wm", "density"]); dpi = density_output.replace("Physical density: ", "") if density_output else "N/A"
        refresh_rate = "N/A"; display_info = self._run_adb_command(["dumpsys", "display"])
        if display_info:
            match = re.search(r'mRefreshRate=([\d.]+)', display_info)
            if match: refresh_rate = match.group(1)
        return {"resolution": resolution, "dpi": dpi, "refresh_rate": refresh_rate}
    def set_display_settings(self, width, height, dpi, refresh_rate):
        all_success = True
        if width and height:
            if self._run_adb_command(["wm", "size", f"{width}x{height}"]) is None: all_success = False
        if dpi:
            if self._run_adb_command(["wm", "density", str(dpi)]) is None: all_success = False
        if refresh_rate:
            if self._run_adb_command(["settings", "put", "system", "peak_refresh_rate", str(refresh_rate)]) is None: all_success = False
            if self._run_adb_command(["settings", "put", "system", "min_refresh_rate", str(refresh_rate)]) is None: all_success = False
        return all_success
    def reset_display_settings(self):
        commands = [["wm", "size", "reset"], ["wm", "density", "reset"], ["settings", "delete", "system", "peak_refresh_rate"], ["settings", "delete", "system", "min_refresh_rate"]]
        results = [self._run_adb_command(cmd) is not None for cmd in commands]; return all(results)
    def get_full_device_info(self):
        all_props_raw = self._run_adb_command(["getprop"], timeout=15);
        if not all_props_raw: return None
        props = {match.groups()[0]: match.groups()[1] for line in all_props_raw.splitlines() if (match := re.match(r'\[(.*?)\]: \[(.*?)\]', line))}
        def get_prop(key, default="N/A"): return props.get(key, default)
        def format_boolean_prop(key, true_val="Sim", false_val="Não"):
            value = get_prop(key)
            if value == "true" or value == "1": return true_val
            if value == "false" or value == "0": return false_val
            return "N/A"
        bootloader_state = get_prop("ro.boot.vbmeta.device_state");
        if bootloader_state == "N/A": bootloader_state = get_prop("ro.boot.verifiedbootstate", "N/A")
        if bootloader_state == "locked": bootloader_status = "Bloqueado"
        elif bootloader_state == "unlocked": bootloader_status = "Desbloqueado"
        else: bootloader_status = "N/A"
        oem_allowed_raw = self._run_adb_command(["settings", "get", "global", "oem_unlocking"])
        if oem_allowed_raw == "1": oem_allowed = "Sim"
        elif oem_allowed_raw == "0": oem_allowed = "Não"
        else: oem_allowed = "Desconhecido"
        battery_info = {}
        battery_dump = self._run_adb_command(["dumpsys", "battery"])
        if battery_dump:
            for line in battery_dump.splitlines():
                line = line.strip()
                if "level:" in line: battery_info["Nível"] = f"{line.split(': ')[1]}%"
                elif "status:" in line: battery_info["Status"] = ["?", "Desconhecido", "Carregando", "Descarregando", "Não está carregando", "Cheia"][int(line.split(': ')[1])]
                elif "health:" in line: battery_info["Saúde"] = ["?", "Desconhecida", "Boa", "Superaquecida", "Morta", "Sobretensão", "Falha não especificada", "Fria"][int(line.split(': ')[1])]
                elif "temperature:" in line: battery_info["Temperatura"] = f"{int(line.split(': ')[1]) / 10}°C"
                elif "voltage:" in line: battery_info["Voltagem"] = f"{int(line.split(': ')[1]) / 1000}V"
        storage_info = {}
        storage_dump = self._run_adb_command(["df", "-h", "/data"])
        if storage_dump and len(storage_dump.splitlines()) > 1:
            parts = storage_dump.splitlines()[1].split()
            if len(parts) >= 5: storage_info["Tamanho Total"], storage_info["Usado"], storage_info["Disponível"], storage_info["Uso%"] = parts[1], parts[2], parts[3], parts[4]
        net_info = {}
        net_dump = self._run_adb_command(["ip", "addr", "show", "wlan0"])
        if net_dump:
            ip_match = re.search(r'inet ([\d\.]+)/\d+', net_dump); mac_match = re.search(r'link/ether ([\w:]+)', net_dump)
            if ip_match: net_info["Endereço IP"] = ip_match.group(1)
            if mac_match: net_info["Endereço MAC"] = mac_match.group(1)
        ram_info_raw = self._run_adb_command(["cat", "/proc/meminfo"])
        match = re.search(r'MemTotal:\s+(\d+)\s+kB', ram_info_raw)
        if match:
            total_kb = int(match.group(1))
            total_gb = total_kb / 1024 / 1024  # converte para GB
            ram_total = f"{total_gb:.2f} GB"
        else:
            ram_total = "N/A"
        info = {
            "Hardware e SoC": {"Modelo": get_prop("ro.product.model"), "Fabricante": get_prop("ro.product.manufacturer"), "Plataforma (Chipset)": get_prop("ro.board.platform"), "Memória RAM Total": ram_total},
            "Software e Build": {"Versão do Android": get_prop("ro.build.version.release"), "Nível da API (SDK)": get_prop("ro.build.version.sdk"), "ID da Build": get_prop("ro.build.id"), "Patch de Segurança": get_prop("ro.build.version.security_patch")},
            "Suporte a GSI & Project Treble": {"Project Treble Habilitado": format_boolean_prop("ro.treble.enabled"), "Seamless Updates (Partição A/B)": format_boolean_prop("ro.build.ab_update"), "System-as-Root": format_boolean_prop("ro.build.system_root_image"), "Arquitetura da CPU": get_prop("ro.product.cpu.abi"), "Versão VNDK": get_prop("ro.vndk.version"), "Suporte a Desbloqueio OEM": format_boolean_prop("ro.oem_unlock_supported", "Sim", "Não Suportado"), "Desbloqueio OEM Permitido": oem_allowed, "Status do Bootloader": bootloader_status,},
            "Display": self.get_current_display_settings(), "Bateria": battery_info, "Armazenamento (/data)": storage_info, "Rede (Wi-Fi)": net_info,
            "Identificadores": {"Número de Série": get_prop("ro.serialno"), "Android ID": self._run_adb_command(["settings", "get", "secure", "android_id"])}
        }
        return info

class DeviceMonitor:
    def __init__(self, adb_path):
        self.adb_path = adb_path
        self._last_cpu_stats = None

    def _run_adb_shell_command(self, command, timeout=5):
        try:
            result = subprocess.run(
                [self.adb_path, "shell"] + command,
                capture_output=True, text=True, timeout=timeout, errors='ignore'
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def get_cpu_usage(self):
        top_output = self._run_adb_shell_command(["top", "-n", "1", "-b"])
        if not top_output: return "N/A"
        
        for line in top_output.splitlines():
            if "CPU" in line:
                match = re.search(r'(\d+)% *user.*, *(\d+)% *sys', line)
                if match:
                    user, sys = int(match.group(1)), int(match.group(2))
                    return f"{user + sys}%"
        return "N/A"

    def get_cpu_usage_percentage(self):
        usage_str = self.get_cpu_usage()
        if usage_str == "N/A": return 0
        try:
            return float(usage_str.replace('%', ''))
        except:
            return 0

    def get_ram_usage(self):
        mem_info = self._run_adb_shell_command(["cat", "/proc/meminfo"])
        if not mem_info: return "N/A", "N/A"

        mem_total_match = re.search(r"MemTotal:\s+(\d+)\s+kB", mem_info)
        mem_available_match = re.search(r"MemAvailable:\s+(\d+)\s+kB", mem_info)

        if not mem_total_match or not mem_available_match: return "N/A", "N/A"

        total_kb = int(mem_total_match.group(1))
        available_kb = int(mem_available_match.group(1))
        used_kb = total_kb - available_kb
        usage_percent = (used_kb / total_kb) * 100
        total_gb, used_gb = total_kb / 1048576, used_kb / 1048576
        
        return f"{usage_percent:.1f}%", f"{used_gb:.2f} / {total_gb:.2f} GB"

    def get_ram_usage_percentage(self):
        usage_str, _ = self.get_ram_usage()
        if usage_str == "N/A": return 0
        try:
            return float(usage_str.replace('%', ''))
        except:
            return 0

    def get_storage_usage(self):
        df_output = self._run_adb_shell_command(["df", "-h", "/data"])
        if df_output and len(df_output.splitlines()) > 1:
            parts = df_output.splitlines()[1].split()
            if len(parts) >= 5: return parts[4], f"{parts[2]} / {parts[1]}"
        return "N/A", "N/A"

    def get_storage_usage_percentage(self):
        usage_str, _ = self.get_storage_usage()
        if usage_str == "N/A": return 0
        try:
            return float(usage_str.replace('%', ''))
        except:
            return 0

    def get_battery_level(self):
        battery_dump = self._run_adb_shell_command(["dumpsys", "battery"])
        if battery_dump:
            for line in battery_dump.splitlines():
                if "level:" in line:
                    try:
                        return int(line.split(': ')[1])
                    except:
                        pass
        return 0

    def get_running_apps(self):
        output = self._run_adb_shell_command(["top", "-n", "1", "-b", "-o", "NAME", "-o", "PID"])
        if not output: return []
        apps = []
        start_index = -1
        for i, line in enumerate(output.splitlines()):
            if "PID" in line and "NAME" in line:
                start_index = i + 1
                break
        if start_index == -1: return []

        for line in output.splitlines()[start_index:]:
            parts = line.split()
            if len(parts) >= 2 and "." in parts[-1]:
                pid = parts[0]
                name = parts[-1]
                apps.append({'pid': pid, 'name': name})
        return apps

    def force_stop_app(self, package_name):
        return self._run_adb_shell_command(["am", "force-stop", package_name])

# --- INTERFACE GRÁFICA ---
def main(page: ft.Page):
    page.title = "Gerenciador ADB Avançado"
    page.window_width, page.window_height = 1100, 720
    page.window_min_width, page.window_min_height = 950, 680
    theme_colors = {"background": "#1e1e2e", "surface": "#313244", "primary": "#89b4fa", "on_primary": "#11111b", "text": "#cdd6f4", "subtext": "#a6adc8", "success": "#a6e3a1", "error": "#f38ba8", "warning": "#f9e2af"}
    page.bgcolor, page.padding, page.theme_mode = theme_colors["background"], 20, ft.ThemeMode.DARK

    ADB, app_manager, config_manager, device_monitor = None, None, None, None
    todos_os_widgets_de_apps = []
    logcat_thread, monitor_thread = None, None
    stop_logcat_event, stop_monitor_event = threading.Event(), threading.Event()
    is_wifi_connected = False
    
    device_name, device_model, device_android, device_manufacturer = ft.Text("-", size=12, color=theme_colors["text"]), ft.Text("-", size=12, color=theme_colors["text"]), ft.Text("-", size=12, color=theme_colors["text"]), ft.Text("-", size=12, color=theme_colors["text"])
    device_status = ft.Text("Inicializando...", size=12, color=theme_colors["subtext"])
    status_indicator = ft.Container(width=10, height=10, bgcolor=theme_colors["subtext"], border_radius=5)
    
    # Dados para os gráficos
    cpu_data = [0] * 60
    ram_data = [0] * 60
    storage_data = [0] * 60
    battery_data = [0] * 60
    monitor_running = False
    
    # Referências para os gráficos
    cpu_chart_ref = None
    ram_chart_ref = None
    storage_chart_ref = None
    battery_chart_ref = None
    
    def inicializar_adb_completo():
        nonlocal ADB, app_manager, config_manager, device_monitor
        ADB, error_msg = localizar_adb()
        if ADB:
            app_manager, config_manager, device_monitor = AppManager(ADB), ConfigManager(ADB), DeviceMonitor(ADB)
            return True
        else:
            page.clean()
            error_details = ft.Text(f"Detalhes: {error_msg}", selectable=True, color=theme_colors["subtext"], size=11)
            page.add(ft.Container(content=ft.Column([ft.Icon(ft.Icons.ERROR_OUTLINE, color=theme_colors["error"], size=48), ft.Text("Falha ao configurar ADB", size=18, weight=ft.FontWeight.BOLD), ft.Text("Verifique sua conexão, permissões da pasta ou antivírus.", size=12, color=theme_colors["subtext"]), ft.Divider(height=10, color="transparent"), error_details, ft.Divider(height=10, color="transparent"), ft.FilledButton("Tentar Novamente", on_click=lambda _: reiniciar_app())], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10), alignment=ft.alignment.center, expand=True))
            return False

    def reiniciar_app(): page.clean(); main(page)
    
    def atualizar_info(e=None):
        nonlocal is_wifi_connected
        if not ADB:
            status_indicator.bgcolor, device_status.value = theme_colors["error"], "ADB não disponível"; page.update(); return
        try:
            devices_result = subprocess.check_output([ADB, "devices"], timeout=5).decode()
            if len(devices_result.strip().split('\n')) > 1 and "device" in devices_result.strip().split('\n')[1]:
                device_line = devices_result.strip().split('\n')[1]
                is_ip = re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', device_line)
                is_wifi_connected = bool(is_ip)

                if is_wifi_connected: wifi_connect_button.text, wifi_connect_button.icon = "Desconectar Wi-Fi", ft.Icons.WIFI_OFF
                else: wifi_connect_button.text, wifi_connect_button.icon = "Conectar via Wi-Fi", ft.Icons.WIFI

                props = subprocess.check_output([ADB, "shell", "getprop"], timeout=10).decode(errors="ignore")
                def get_prop(key):
                    for line in props.splitlines():
                        if key in line: return line.split("]: [")[-1].replace("]", "")
                    return "N/A"
                device_name.value, device_model.value, device_android.value, device_manufacturer.value = get_prop('ro.product.name'), get_prop('ro.product.model'), f"Android {get_prop('ro.build.version.release')}", get_prop('ro.product.manufacturer')
                status_indicator.bgcolor, device_status.value = theme_colors["success"], "Dispositivo Conectado"
            else:
                is_wifi_connected, wifi_connect_button.text, wifi_connect_button.icon = False, "Conectar via Wi-Fi", ft.Icons.WIFI
                device_name.value, device_model.value, device_android.value, device_manufacturer.value = "-", "-", "-", "-"; status_indicator.bgcolor, device_status.value = theme_colors["error"], "Nenhum dispositivo"
        except Exception:
            is_wifi_connected, wifi_connect_button.text, wifi_connect_button.icon = False, "Conectar via Wi-Fi", ft.Icons.WIFI
            device_name.value, device_model.value, device_android.value, device_manufacturer.value = "-", "-", "-", "-"; status_indicator.bgcolor, device_status.value = theme_colors["error"], "Erro de conexão"
        page.update()
    
    def conectar_wifi_automatico(e):
        def get_connected_ips():
            try:
                output = subprocess.check_output([ADB, "devices"], text=True)
                # Pega os dispositivos com IP na porta 5555
                connected = [line.split()[0] for line in output.splitlines() if ":5555" in line and "device" in line]
                return connected
            except Exception:
                return []

        connected_ips = get_connected_ips()
        
        if connected_ips:
            # Se já conectado, perguntar se quer desconectar
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Desconectar ADB via Wi-Fi"),
                content=ft.Text(f"Dispositivo conectado via Wi-Fi ({connected_ips[0]}). Deseja desconectar?"),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: setattr(dialog, 'open', False) or page.update()),
                    ft.FilledButton("Desconectar", on_click=lambda _: disconnect_wifi(dialog, connected_ips[0])),
                ],
                actions_alignment=ft.MainAxisAlignment.END
            )
        else:
            # Se não conectado, oferecer conexão
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Ativar ADB via Wi-Fi"),
                content=ft.Column([
                    ft.Text("Este processo tentará ativar e conectar ao ADB via Wi-Fi automaticamente."),
                    ft.Text("Para isso, seu dispositivo DEVE estar conectado via USB agora.", weight=ft.FontWeight.BOLD),
                    ft.Text("Após a confirmação, você poderá desconectar o cabo USB."),
                ], height=200),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: setattr(dialog, 'open', False) or page.update()),
                    ft.FilledButton("Ativar e Conectar", on_click=lambda _: run_wifi_connection_flow(dialog)),
                ],
                actions_alignment=ft.MainAxisAlignment.END
            )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()


    def disconnect_wifi(dialog, device_ip):
        dialog.open = False
        page.update()
        try:
            subprocess.run([ADB, "disconnect", f"{device_ip}"], check=True, capture_output=True, text=True, timeout=10)
            page.snack_bar = ft.SnackBar(content=ft.Text(f"Desconectado {device_ip} com sucesso!"), bgcolor=theme_colors["success"])
            atualizar_info()
        except Exception as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(f"Falha ao desconectar: {ex}"), bgcolor=theme_colors["error"])
        page.snack_bar.open = True
        page.update()

    def run_wifi_connection_flow(dialog):
        dialog.open = False
        page.update()
        threading.Thread(target=_wifi_connection_task, daemon=True).start()

    def _wifi_connection_task():
        page.snack_bar = ft.SnackBar(content=ft.Text("Passo 1/3: Ativando modo TCP/IP na porta 5555..."), bgcolor=theme_colors["primary"])
        page.snack_bar.open = True; page.update()
        try:
            subprocess.run([ADB, "tcpip", "5555"], check=True, capture_output=True, timeout=10)
        except Exception:
            page.snack_bar = ft.SnackBar(content=ft.Text("Falha: Certifique-se que o dispositivo está conectado via USB."), bgcolor=theme_colors["error"])
            page.snack_bar.open = True; page.update()
            return
        
        threading.Event().wait(1)

        page.snack_bar = ft.SnackBar(content=ft.Text("Passo 2/3: Buscando endereço IP do dispositivo..."), bgcolor=theme_colors["primary"])
        page.snack_bar.open = True; page.update()
        device_ip = None
        try:
            net_dump = config_manager._run_adb_command(["ip", "addr", "show", "wlan0"])
            if net_dump:
                ip_match = re.search(r'inet ([\d\.]+)/\d+', net_dump)
                if ip_match: device_ip = ip_match.group(1)
            if not device_ip: raise Exception("Não foi possível encontrar o IP. Verifique se o Wi-Fi está ligado.")
        except Exception as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(f"Falha ao buscar IP: {ex}"), bgcolor=theme_colors["error"])
            page.snack_bar.open = True; page.update()
            return

        page.snack_bar = ft.SnackBar(content=ft.Text(f"Passo 3/3: Conectando a {device_ip}:5555..."), bgcolor=theme_colors["primary"])
        page.snack_bar.open = True; page.update()
        try:
            result = subprocess.run([ADB, "connect", f"{device_ip}:5555"], check=True, capture_output=True, text=True, timeout=10)
            if "connected" in result.stdout or "already connected" in result.stdout:
                 page.snack_bar = ft.SnackBar(content=ft.Text(f"Conectado com sucesso a {device_ip}!"), bgcolor=theme_colors["success"])
                 atualizar_info()
            else:
                raise Exception(result.stdout or "Resposta de conexão inesperada.")
        except Exception as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(f"Falha ao conectar: {ex}"), bgcolor=theme_colors["error"])
        
        page.snack_bar.open = True; page.update()

    # --- Funções da Aba de Apps ---
    def deletar_app(pkg_name, e):
        page = e.page; print(f"--- Iniciando remoção do pacote: {pkg_name} ---")
        if not ADB: print(f"[ERRO] A conexão ADB não está ativa. Impossível remover {pkg_name}."); return
        command = [ADB, "shell", "pm", "uninstall", "--user", "0", pkg_name]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
            print(f"[SUCESSO] Pacote '{pkg_name}' desinstalado.")
            if result.stdout: print(f"   |-- Saída do ADB: {result.stdout.strip()}")
            todos_os_widgets_de_apps[:] = [item for item in todos_os_widgets_de_apps if item.data != pkg_name]
            filtrar_apps(e)
            page.snack_bar = ft.SnackBar(content=ft.Text(f"App '{pkg_name}' desinstalado com sucesso."), bgcolor=theme_colors["success"])
            page.snack_bar.open = True; page.update()
        except subprocess.CalledProcessError as ex:
            error_output = ex.stderr.strip(); print(f"[FALHA] O comando para desinstalar '{pkg_name}' falhou."); print(f"   |-- Erro retornado pelo ADB: {error_output}")
            page.snack_bar = ft.SnackBar(content=ft.Text(f"Falha ao remover: {error_output}"), bgcolor=theme_colors["error"])
            page.snack_bar.open = True; page.update()
        except Exception as ex:
            print(f"[ERRO] Um erro inesperado ocorreu ao tentar remover '{pkg_name}': {ex}")
            page.snack_bar = ft.SnackBar(content=ft.Text(f"Erro inesperado: {ex}"), bgcolor=theme_colors["error"])
            page.snack_bar.open = True; page.update()

    def carregar_apps_otimizado(e=None):
        nonlocal todos_os_widgets_de_apps
        if not ADB or not app_manager: apps_list.visible=True; apk_installer_view.visible=False; apps_list.controls.clear(); apps_list.controls.append(ft.Text("ADB não disponível", color=theme_colors["error"])); page.update(); return
        apps_list.visible = True; apk_installer_view.visible = False
        apps_list.controls.clear(); todos_os_widgets_de_apps.clear(); campo_pesquisa.value = ""
        apps_list.controls.append(ft.Row([ft.ProgressRing(width=20, height=20), ft.Text("Carregando lista de apps...")], alignment=ft.MainAxisAlignment.CENTER)); page.update()
        try:
            param = [""]
            if (Paramentro_de_Carregamento.value == False):
                param = [""]
            else:
                param = ["-3"]
            print(param)
            packages = subprocess.check_output([ADB, "shell", "pm", "list", "packages"] + param, timeout=20).decode(errors="ignore")
            packages = [p.replace("package:", "").strip() for p in packages.splitlines() if p.strip()]
            if not packages: apps_list.controls.clear(); apps_list.controls.append(ft.Text("Nenhum aplicativo encontrado.", color=theme_colors["subtext"])); page.update(); return
            app_infos = app_manager.get_app_info_batch_no_icons(packages)
            apps_list.controls.clear(); package_to_image_map = {}
            for info in sorted(app_infos, key=lambda x: x['name'].lower()):
                #icon_image = ft.Image(src=app_manager.default_icon_b64, width=36, height=36, fit=ft.ImageFit.CONTAIN, border_radius=6)
                #package_to_image_map[info['package']] = icon_image
                list_item = ft.Container(
                    content=ft.ListTile(
                        #leading=icon_image,
                        title=ft.Text(info["name"], size=13, weight=ft.FontWeight.W_500, color=theme_colors["text"]),
                        subtitle=ft.Text(f"Pacote: {info['package']}", size=10, color=theme_colors["subtext"]),
                        trailing=ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme_colors["subtext"], tooltip="Remover App", on_click=lambda e, p=info['package']: deletar_app(p, e))
                    ),
                    border_radius=8, on_hover=lambda e: setattr(e.control, 'bgcolor', theme_colors["surface"] if e.data == "true" else "transparent") or e.control.update(), padding=ft.padding.only(left=5, right=5), data=info['package']
                )
                todos_os_widgets_de_apps.append(list_item)
            apps_list.controls = todos_os_widgets_de_apps
            page.update()
            #threading.Thread(target=carregar_icones_em_background, args=(package_to_image_map,), daemon=True).start()
        except Exception as ex: apps_list.controls.clear(); apps_list.controls.append(ft.Text(f"Erro ao carregar apps: {ex}", color=theme_colors["error"])); page.update()

    def carregar_icones_em_background(package_map):
        for package_name, image_widget in package_map.items():
            icon_src = app_manager.get_app_icon(package_name)
            if image_widget.src != icon_src: image_widget.src = icon_src; page.update()

    def filtrar_apps(e):
        termo_de_busca = e.control.value.lower() if e.control.value else ""
        if not termo_de_busca: apps_list.controls = todos_os_widgets_de_apps
        else: apps_list.controls = [widget for widget in todos_os_widgets_de_apps if termo_de_busca in widget.content.title.value.lower() or termo_de_busca in widget.content.subtitle.value.lower()]
        page.update()

    def show_apk_installer_view(e): apps_list.visible = False; apk_installer_view.visible = True; page.update()
    def shizuku_active(e):
        def fechar_dialog():
            dialog.open = False
            page.update()

        def detectar_arquitetura(COMMANDO):
            """Detecta a arquitetura do dispositivo para baixar o APK correto"""
            try:
                # Obter a arquitetura do processador
                arch_output = COMMANDO._run_adb_shell_command(["uname", "-m"])
                if not arch_output:
                    # Fallback: usar getprop
                    arch_output = COMMANDO._run_adb_shell_command(["getprop", "ro.product.cpu.abi"])
                
                arch = arch_output.strip().lower() if arch_output else "arm64-v8a"
                
                # Mapear arquiteturas para os sufixos do Shizuku
                arch_map = {
                    "arm64": "arm64-v8a",
                    "aarch64": "arm64-v8a", 
                    "arm64-v8a": "arm64-v8a",
                    "arm": "armeabi-v7a",
                    "armeabi-v7a": "armeabi-v7a",
                    "x86_64": "x86_64",
                    "x86": "x86"
                }
                
                for key, value in arch_map.items():
                    if key in arch:
                        return value
                
                return "arm64-v8a"  # padrão mais comum
                
            except Exception as ex:
                print(f"❌ Erro ao detectar arquitetura: {ex}")
                return "arm64-v8a"

        def baixar_instalar_shizuku(COMMANDO):
            try:
                # 1. Detectar arquitetura do dispositivo
                arquitetura = detectar_arquitetura(COMMANDO)
                print(f"📱 Arquitetura detectada: {arquitetura}")
                
                # 2. Obter última versão no GitHub
                url = "https://api.github.com/repos/RikkaApps/Shizuku/releases/latest"
                response = requests.get(url)
                release = response.json()

                # 3. Encontrar o APK correto para a arquitetura
                apk_url = None
                apk_name = None
                
                for asset in release["assets"]:
                    asset_name = asset["name"]
                    # Procurar por APKs que correspondam à arquitetura
                    if (asset_name.endswith(".apk") and 
                        (arquitetura in asset_name.lower() or 
                        "universal" in asset_name.lower() or
                        "noarch" in asset_name.lower())):
                        
                        # Priorizar APK universal, depois específico da arquitetura
                        if "universal" in asset_name.lower() or "noarch" in asset_name.lower():
                            apk_url = asset["browser_download_url"]
                            apk_name = asset_name
                            break
                        elif arquitetura in asset_name.lower():
                            apk_url = asset["browser_download_url"]
                            apk_name = asset_name
                
                # Fallback: pegar qualquer APK se não encontrou específico
                if not apk_url:
                    for asset in release["assets"]:
                        if asset["name"].endswith(".apk"):
                            apk_url = asset["browser_download_url"]
                            apk_name = asset["name"]
                            break

                if not apk_url:
                    print("❌ Não foi possível encontrar o APK do Shizuku na última release.")
                    return False

                print(f"📦 APK selecionado: {apk_name}")

                # 4. Baixar o APK
                apk_path = f"shizuku-{arquitetura}.apk"
                print(f"⬇️ Baixando {apk_url} ...")
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                r = requests.get(apk_url, headers=headers, stream=True)
                
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0
                
                with open(apk_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                print(f"📥 Progresso: {percent:.1f}%", end='\r')

                print("\n✅ Download concluído!")

                # 5. Instalar no dispositivo
                print("📲 Instalando Shizuku no dispositivo...")
                
                # Usar subprocess diretamente para instalação ADB
                import subprocess
                adb_path = localizar_adb()[0]
                install_result = subprocess.run([
                    adb_path, "install", "-r", "-g", apk_path
                ], capture_output=True, text=True, timeout=60)
                
                print(f"✅ Instalação concluída! Status: {install_result.returncode}")
                print(f"Saída: {install_result.stdout}")
                if install_result.stderr:
                    print(f"Erros: {install_result.stderr}")

                # 6. Limpar arquivo temporário
                if os.path.exists(apk_path):
                    os.remove(apk_path)
                    
                return install_result.returncode == 0

            except subprocess.TimeoutExpired:
                print("❌ Timeout na instalação do APK")
                return False
            except Exception as ex:
                print(f"❌ Erro ao baixar/instalar Shizuku: {ex}")
                return False
            
        def obter_caminho_shizuku_dinamico(COMMANDO):
            """Obtém o caminho dinâmico da biblioteca libshizuku.so"""
            try:
                # 1. Obter o caminho de instalação do package
                package_path_output = COMMANDO._run_adb_shell_command([
                    "pm", "path", "moe.shizuku.privileged.api"
                ])
                
                if not package_path_output:
                    print("❌ Shizuku não está instalado ou não encontrado")
                    return None
                    
                # 2. Extrair o caminho base
                for line in package_path_output.splitlines():
                    if line.startswith("package:"):
                        base_path = line.replace("package:", "").strip()
                        print(f"📁 Caminho base encontrado: {base_path}")
                        
                        # 3. Extrair o diretório base (remover /base.apk)
                        base_dir = base_path.replace("/base.apk", "")
                        
                        # 4. Detectar arquitetura
                        arch_output = COMMANDO._run_adb_shell_command(["getprop", "ro.product.cpu.abi"])
                        arch = arch_output.strip().lower() if arch_output else "arm64-v8a"
                        
                        # 5. Construir caminho da biblioteca
                        if "arm64" in arch or "aarch64" in arch:
                            lib_path = f"{base_dir}/lib/arm64/libshizuku.so"
                        elif "arm" in arch:
                            lib_path = f"{base_dir}/lib/arm/libshizuku.so"
                        elif "x86_64" in arch:
                            lib_path = f"{base_dir}/lib/x86_64/libshizuku.so"
                        elif "x86" in arch:
                            lib_path = f"{base_dir}/lib/x86/libshizuku.so"
                        else:
                            lib_path = f"{base_dir}/lib/arm64/libshizuku.so"  # fallback
                        
                        # 6. Verificar se a biblioteca existe
                        check_lib = COMMANDO._run_adb_shell_command(["ls", lib_path])
                        if check_lib and "No such file" not in check_lib and "not found" not in check_lib:
                            print(f"✅ Biblioteca encontrada: {lib_path}")
                            return lib_path
                        else:
                            print(f"❌ Biblioteca não encontrada em: {lib_path}")
                            
                return None
                
            except Exception as ex:
                print(f"❌ Erro ao obter caminho dinâmico: {ex}")
                return None
        def obter_caminho_shizuku_automatico(COMMANDO):
            """Tenta todos os métodos para encontrar o caminho da biblioteca"""
            
            # Método 1: Package path (mais confiável)
            caminho = obter_caminho_shizuku_dinamico(COMMANDO)
            if caminho:
                return caminho
            
                
            print("❌ Não foi possível encontrar a biblioteca libshizuku.so")
            return None

        def Verificar(e):
            try:
                COMMANDO = DeviceMonitor(localizar_adb()[0])
                packages = COMMANDO._run_adb_shell_command(["pm", "list", "packages"])
                encontrado = False

                if packages:
                    for line in packages.splitlines():
                        if "moe.shizuku.privileged.api" in line:
                            encontrado = True

                            # Descobrir a activity principal
                            activity_output = COMMANDO._run_adb_shell_command([
                                "cmd", "package", "resolve-activity", "--brief", "moe.shizuku.privileged.api"
                            ])
                            activity = activity_output.strip().splitlines()[-1]

                            if not activity:
                                print("⚠️ Não foi possível determinar a activity do Shizuku.")
                                fechar_dialog()
                                return

                            # Iniciar o Shizuku
                            print("Iniciando serviço Shizuku...")
                            result = COMMANDO._run_adb_shell_command([
                                "am", "start", "-n", activity
                            ])

                            if result:
                                print("✅ Shizuku iniciado e interface aberta!")

                                # OBTER CAMINHO DINÂMICO DA BIBLIOTECA
                                caminho_lib = obter_caminho_shizuku_dinamico(COMMANDO)
                                
                                if caminho_lib:
                                    print(f"🎯 Executando biblioteca: {caminho_lib}")
                                    ativar_o_shinzuku = COMMANDO._run_adb_shell_command([caminho_lib])
                                    
                                    if ativar_o_shinzuku:
                                        msg = "Shizuku ativado com sucesso!"
                                    else:
                                        msg = "Biblioteca executada mas ativação pode ter falhado."
                                else:
                                    msg = "Não foi possível encontrar a biblioteca do Shizuku."
                                
                                # Mostrar diálogo com resultado
                                aviso = ft.AlertDialog(
                                    modal=True,
                                    title=ft.Text("Resultado da Ativação"),
                                    content=ft.Text(msg),
                                    actions=[ft.FilledButton("Ok", on_click=lambda _: setattr(aviso, 'open', False) or page.update())],
                                    actions_alignment=ft.MainAxisAlignment.END
                                )
                                page.overlay.append(aviso)
                                aviso.open = True
                                page.update()

                            else:
                                print("⚠️ Serviço iniciado, mas interface não abriu")

                            fechar_dialog()
                            break

                if not encontrado:
                    print("❌ Shizuku não está instalado. Baixando do GitHub...")
                    if baixar_instalar_shizuku(COMMANDO):
                        print("✅ Shizuku instalado com sucesso! Tente novamente.")
                        # Mostrar mensagem para tentar novamente
                        aviso = ft.AlertDialog(
                            modal=True,
                            title=ft.Text("Instalação Concluída"),
                            content=ft.Text("Shizuku foi instalado com sucesso! Clique em 'Ativar o Shizuku' novamente para completar a ativação."),
                            actions=[ft.FilledButton("Ok", on_click=lambda _: setattr(aviso, 'open', False) or page.update())],
                            actions_alignment=ft.MainAxisAlignment.END
                        )
                        page.overlay.append(aviso)
                        aviso.open = True
                        page.update()
                    else:
                        print("❌ Falha ao instalar Shizuku automaticamente.")
                        aviso = ft.AlertDialog(
                            modal=True,
                            title=ft.Text("Erro na Instalação"),
                            content=ft.Text("Não foi possível instalar o Shizuku automaticamente. Por favor, instale manualmente."),
                            actions=[ft.FilledButton("Ok", on_click=lambda _: setattr(aviso, 'open', False) or page.update())],
                            actions_alignment=ft.MainAxisAlignment.END
                        )
                        page.overlay.append(aviso)
                        aviso.open = True
                        page.update()

            except Exception as ex:
                print(f"❌ Erro: {ex}")
                fechar_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Ativar o Shizuku"),
            content=ft.Text("Isso abrirá o Shizuku em primeiro plano para você configurar."),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: setattr(dialog, 'open', False) or page.update()),
                ft.FilledButton("Ativar o Shizuku", on_click=Verificar),
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )

        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    def hide_apk_installer_view(e): apps_list.visible = True; apk_installer_view.visible = False; page.update()
    def _install_apk_task(apk_path):
        installer_progress_ring.visible = True; installer_icon.visible = False
        installer_text.value = f"Instalando {os.path.basename(apk_path)}..."; page.update()
        try:
            subprocess.run([ADB, "install", "-r", apk_path], capture_output=True, text=True, timeout=300, check=True)
            page.snack_bar = ft.SnackBar(content=ft.Text(f"App instalado com sucesso!"), bgcolor=theme_colors["success"])
        except subprocess.CalledProcessError as e: page.snack_bar = ft.SnackBar(content=ft.Text(f"Falha na instalação: {e.stderr.strip()}"), bgcolor=theme_colors["error"])
        except Exception as e: page.snack_bar = ft.SnackBar(content=ft.Text(f"Erro inesperado: {e}"), bgcolor=theme_colors["error"])
        finally:
            installer_progress_ring.visible = False; installer_icon.visible = True
            installer_text.value = "Arraste e solte o APK aqui ou clique para selecionar"
            page.snack_bar.open = True; page.update()
    def install_apk(path): threading.Thread(target=_install_apk_task, args=(path,), daemon=True).start()
    def on_apk_picked(e: ft.FilePickerResultEvent):
        if e.files and e.files[0].path: install_apk(e.files[0].path)
    def on_drag_accept(e: ft.DragTargetEvent):
        if e.data.startswith("file://"):
            apk_path = e.data[7:]; e.control.content.border = None
            install_apk(apk_path); page.update()
    def on_drag_will_accept(e): e.control.content.border = ft.border.all(2, theme_colors["primary"]); page.update()
    def on_drag_leave(e): e.control.content.border = ft.border.all(1, theme_colors["subtext"]); page.update()
    def update_logcat_view(log_list_view, stop_event):
        try:
            process = subprocess.Popen([ADB, "logcat", "-v", "brief"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="ignore")
            while not stop_event.is_set():
                line = process.stdout.readline()
                if not line: break
                color = theme_colors["subtext"]
                if line.startswith("E/"): color = theme_colors["error"]
                elif line.startswith("W/"): color = theme_colors["warning"]
                log_list_view.controls.append(ft.Text(line.strip(), font_family="monospace", size=11, color=color))
                if len(log_list_view.controls) > 500: log_list_view.controls.pop(0)
                page.update()
            process.terminate()
        except Exception as ex: print(f"Erro no logcat: {ex}")

    def start_stop_logcat(e):
        nonlocal logcat_thread
        if logcat_thread and logcat_thread.is_alive():
            stop_logcat_event.set(); logcat_thread.join(); logcat_thread = None
            logcat_toggle_button.icon, logcat_toggle_button.text = ft.Icons.PLAY_ARROW, "Iniciar"
        else:
            stop_logcat_event.clear(); logcat_list.controls.clear()
            logcat_thread = threading.Thread(target=update_logcat_view, args=(logcat_list, stop_logcat_event), daemon=True)
            logcat_thread.start()
            logcat_toggle_button.icon, logcat_toggle_button.text = ft.Icons.STOP, "Parar"
        page.update()

    def clear_logcat(e): logcat_list.controls.clear(); page.update()
    def _executar_comando_dispositivo(e, comando, titulo, msg, sucesso_msg):
        page = e.page
        def acao_confirmada(e_inner):
            page.dialog.open = False
            page.snack_bar = ft.SnackBar(content=ft.Text(f"{sucesso_msg}..."), bgcolor=theme_colors["primary"])
            page.snack_bar.open = True; page.update()
            try: subprocess.run([ADB] + comando, capture_output=True, text=True, timeout=15)
            except Exception as ex: print(f"Erro ao executar comando: {ex}")
        page.dialog = ft.AlertDialog(modal=True, title=ft.Text(titulo), content=ft.Text(msg), actions=[ft.TextButton("Cancelar", on_click=lambda e_inner: setattr(page.dialog, 'open', False) or page.update()), ft.FilledButton("Confirmar", style=ft.ButtonStyle(bgcolor=theme_colors["error"]), on_click=acao_confirmada)], actions_alignment=ft.MainAxisAlignment.END)
        page.dialog.open = True; page.update()

    def handle_power_off(e): _executar_comando_dispositivo(e, ["shell", "reboot", "-p"], "Desligar Dispositivo", "Você tem certeza que deseja desligar o dispositivo conectado?", "Enviando comando para desligar")
    def handle_reboot(e): _executar_comando_dispositivo(e, ["reboot"], "Reiniciar Dispositivo", "Você tem certeza que deseja reiniciar o dispositivo conectado?", "Enviando comando para reiniciar")
    def handle_reboot_fastboot(e): _executar_comando_dispositivo(e, ["reboot", "bootloader"], "Reiniciar em Modo Fastboot", "Você tem certeza que deseja reiniciar em modo Fastboot/Bootloader?", "Enviando comando para reiniciar em fastboot")

    def executar_scrcpy(scrcpy_path: str, args=None):
        if args is None:
            args = []
        scrcpy_exe = Path(scrcpy_path)

        if not scrcpy_exe.exists():
            raise FileNotFoundError(f"scrcpy não encontrado em {scrcpy_exe}")

        # executa scrcpy com os argumentos
        subprocess.run([str(scrcpy_exe), *args])
        
    # Adicione esta variável global no início do arquivo (após os imports)
    

    # Modifique a função executar_espelhamento para bloquear a interface sc scrcpy --otgrcpy --otg
    def executar_espelhamento(e):
        global ESPELHAMENTO_ATIVO
        if ESPELHAMENTO_ATIVO:
            page.snack_bar = ft.SnackBar(content=ft.Text("Espelhamento já está ativo!"), bgcolor=theme_colors["warning"])
            page.snack_bar.open = True; page.update(); return
        
        def run_scrcpy_task():
            global ESPELHAMENTO_ATIVO
            try:
                # 1. Configurar bloqueio de UI e mensagem de início
                ESPELHAMENTO_ATIVO = True
                bloquear_interface(True)
                page.snack_bar = ft.SnackBar(content=ft.Text("Iniciando espelhamento de tela..."), bgcolor=theme_colors["primary"])
                page.snack_bar.open = True; page.update()
                
                # 2. Obter ferramentas (mantido da sua lógica)
                adb_manager = ADBManager()
                tools, err = adb_manager.get_tools()
                if err: raise Exception(f"Erro ao preparar ferramentas: {err}")
                scrcpy_path = tools['scrcpy']

                # 3. Execução real do scrcpy
                # Corrigir --bit-rate para --video-bit-rate
                args = ["--turn-screen-off", "--max-size", "1024", "--video-bit-rate", "8M"]
                
                # Executa o scrcpy - O bloqueio da Thread é aqui até o scrcpy fechar
                subprocess.run([str(scrcpy_path), *args])

            except Exception as ex:
                page.snack_bar = ft.SnackBar(content=ft.Text(f"Erro ao iniciar espelhamento: {ex}"), bgcolor=theme_colors["error"])
                page.snack_bar.open = True; page.update()
            finally:
                # 4. Desbloquear UI e reverter o estado
                ESPELHAMENTO_ATIVO = False
                bloquear_interface(False)
                page.snack_bar = ft.SnackBar(content=ft.Text("Espelhamento encerrado."), bgcolor=theme_colors["subtext"])
                page.snack_bar.open = True; page.update()
        
        # Executar a função que contém o subprocess.run em uma thread
        threading.Thread(target=run_scrcpy_task, daemon=True).start()

    # Adicione esta função para bloquear/desbloquear a interface
    def bloquear_interface(bloquear):
        """Bloqueia ou desbloqueia a interface durante o espelhamento"""
        if bloquear:
            # Desabilitar todos os botões e controles
            espelhar_tela_button.disabled = True
            wifi_connect_button.disabled = True
            power_controls.disabled = True
            tabs.disabled = True
            
            # Adicionar overlay de bloqueio
            if not any(isinstance(control, ft.Container) and hasattr(control, 'bgcolor') and control.bgcolor == ft.Colors.with_opacity(0.7, ft.Colors.BLACK) for control in page.controls):
                overlay = ft.Container(
                    bgcolor=ft.Colors.with_opacity(0.7, ft.Colors.BLACK),
                    expand=True,
                    content=ft.Column([
                        ft.Icon(ft.Icons.SCREEN_SHARE, size=64, color=theme_colors["primary"]),
                        ft.Text("Espelhamento Ativo", size=24, weight=ft.FontWeight.BOLD),
                        ft.Text("A interface está bloqueada durante o espelhamento", size=16),
                        ft.Text("Feche a janela do scrcpy para liberar", size=14, color=theme_colors["subtext"])
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=20),
                    alignment=ft.alignment.center
                )
                page.overlay.append(overlay)
        else:
            # Reabilitar controles
            espelhar_tela_button.disabled = False
            wifi_connect_button.disabled = False
            power_controls.disabled = False
            tabs.disabled = False
            
            # Remover overlay
            page.overlay = [control for control in page.overlay if not (isinstance(control, ft.Container) and hasattr(control, 'bgcolor') and control.bgcolor == ft.Colors.with_opacity(0.7, ft.Colors.BLACK))]
        
        page.update()

    def carregar_configuracoes_atuais(e=None):
        if not config_manager: return
        settings = config_manager.get_current_display_settings()
        current_resolution.value, current_dpi.value, current_refresh_rate.value = f"{settings['resolution']}", f"{settings['dpi']}", f"{settings['refresh_rate']}"
        try:
            if "x" in settings['resolution']:
                width, height = settings['resolution'].split("x"); width_slider.value, width_field.value = float(width), width; height_slider.value, height_field.value = float(height), height
            if settings['dpi'] != "N/A": dpi_slider.value, dpi_field.value = float(settings['dpi']), settings['dpi']
            if settings['refresh_rate'] != "N/A":
                rate = float(settings['refresh_rate'].split('.')[0]); refresh_slider.value, refresh_field.value = rate, str(int(rate))
        except Exception as ex: print(f"Erro ao parsear configurações: {ex}")
        page.update()
    def aplicar_configuracoes(e):
        if not config_manager: return
        page.snack_bar = ft.SnackBar(content=ft.Text("Aplicando configurações..."), bgcolor=theme_colors["primary"]); page.snack_bar.open = True; page.update()
        success = config_manager.set_display_settings(width=int(width_field.value), height=int(height_field.value), dpi=int(dpi_field.value), refresh_rate=float(refresh_field.value))
        page.snack_bar = ft.SnackBar(content=ft.Text("Configurações aplicadas com sucesso!", color=theme_colors["on_primary"]), bgcolor=theme_colors["success"]) if success else ft.SnackBar(content=ft.Text("Erro ao aplicar. Verifique o console.", color=theme_colors["on_primary"]), bgcolor=theme_colors["error"])
        page.snack_bar.open = True; carregar_configuracoes_atuais(); page.update()
    def resetar_configuracoes(e):
        if not config_manager: return
        def confirmar_reset(e):
            page.dialog.open = False; page.update()
            if config_manager.reset_display_settings():
                page.snack_bar = ft.SnackBar(content=ft.Text("Configurações resetadas para o padrão!", color=theme_colors["on_primary"]), bgcolor=theme_colors["success"]); carregar_configuracoes_atuais()
            else:
                page.snack_bar = ft.SnackBar(content=ft.Text("Erro ao resetar. Verifique o console.", color=theme_colors["on_primary"]), bgcolor=theme_colors["error"])
            page.snack_bar.open = True; page.update()
        page.dialog = ft.AlertDialog(modal=True, title=ft.Text("Confirmar Reset"), content=ft.Text("Deseja resetar as configurações de tela para o padrão?"), actions=[ft.TextButton("Cancelar", on_click=lambda e: setattr(page.dialog, 'open', False) or page.update()), ft.FilledButton("Resetar", style=ft.ButtonStyle(bgcolor=theme_colors["warning"], color=theme_colors["background"]), on_click=confirmar_reset)], actions_alignment=ft.MainAxisAlignment.END, shape=ft.RoundedRectangleBorder(radius=10), bgcolor=theme_colors["surface"])
        page.dialog.open = True; page.update()
    def load_device_info(e=None):
        info_content_area.controls = [ft.Row([ft.ProgressRing(), ft.Text("Carregando informações...")], alignment=ft.MainAxisAlignment.CENTER, spacing=10)]; page.update()
        if not config_manager:
            info_content_area.controls = [ft.Text("ADB não conectado.", color=theme_colors["error"])]; page.update(); return
        all_info = config_manager.get_full_device_info()
        info_content_area.controls.clear()
        if not all_info:
            info_content_area.controls = [ft.Text("Não foi possível obter as informações do dispositivo.", color=theme_colors["error"])]
        else:
            for category_title, category_data in all_info.items():
                card = create_info_card(category_title, category_data)
                if card: info_content_area.controls.append(card)
        page.update()

    # --- NOVAS FUNÇÕES PARA A ABA DE MONITORAMENTO CORRIGIDAS ---
    def create_chart(data, color, title, max_value=100):
        """Cria um gráfico de linha para exibir dados em tempo real"""
        if not data: 
            return ft.Container(
                content=ft.Text("Sem dados", color=theme_colors["subtext"]),
                padding=10,
                border_radius=8,
                bgcolor=theme_colors["surface"],
                expand=True,
            )
        
        points = []
        for i, value in enumerate(data):
            if value is not None:
                y = max(0, min(100, value))
                points.append(ft.LineChartDataPoint(i, 100 - y))
        
        chart = ft.LineChart(
            data_series=[
                ft.LineChartData(
                    data_points=points,
                    stroke_width=2,
                    color=color,
                    curved=True,
                    stroke_cap_round=True,
                )
            ],
            border=ft.border.all(1, ft.Colors.with_opacity(0.2, color)),
            left_axis=ft.ChartAxis(labels_size=40),
            bottom_axis=ft.ChartAxis(labels_size=0),
            tooltip_bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.GREY_900),
            min_y=0,
            max_y=100,
            expand=True,
            height=120,
        )
        
        return ft.Container(
            content=ft.Column([
                ft.Text(title, size=14, weight=ft.FontWeight.BOLD),
                chart
            ], spacing=5),
            padding=10,
            border_radius=8,
            bgcolor=theme_colors["surface"],
            expand=True,
        )

    def update_monitor_data():
        """Atualiza os dados de monitoramento em tempo real"""
        nonlocal cpu_data, ram_data, storage_data, battery_data, monitor_running
        
        while monitor_running:
            if device_monitor and ADB:
                try:
                    # Coleta dados atuais
                    cpu_current = device_monitor.get_cpu_usage_percentage()
                    ram_current = device_monitor.get_ram_usage_percentage()
                    storage_current = device_monitor.get_storage_usage_percentage()
                    battery_current = device_monitor.get_battery_level()
                    
                    # Atualiza os arrays de dados
                    cpu_data.append(cpu_current)
                    ram_data.append(ram_current)
                    storage_data.append(storage_current)
                    battery_data.append(battery_current)
                    
                    # Mantém apenas os últimos 60 pontos
                    if len(cpu_data) > 60: cpu_data = cpu_data[-60:]
                    if len(ram_data) > 60: ram_data = ram_data[-60:]
                    if len(storage_data) > 60: storage_data = storage_data[-60:]
                    if len(battery_data) > 60: battery_data = battery_data[-60:]
                    
                    # Atualiza os valores de texto
                    cpu_value_text.value = f"{cpu_current:.1f}%"
                    ram_value_text.value = f"{ram_current:.1f}%"
                    storage_value_text.value = f"{storage_current:.1f}%"
                    battery_value_text.value = f"{battery_current}%"
                    
                    # Atualiza os gráficos usando referências
                    if cpu_chart_ref:
                        cpu_chart_ref.content = create_chart(cpu_data, theme_colors["primary"], "CPU").content
                    if ram_chart_ref:
                        ram_chart_ref.content = create_chart(ram_data, theme_colors["success"], "RAM").content
                    if storage_chart_ref:
                        storage_chart_ref.content = create_chart(storage_data, theme_colors["warning"], "Armazenamento").content
                    if battery_chart_ref:
                        battery_chart_ref.content = create_chart(battery_data, theme_colors["error"], "Bateria", 100).content
                    
                    page.update()
                    
                except Exception as e:
                    print(f"Erro ao coletar dados de monitoramento: {e}")
            
            time.sleep(2)

    def start_stop_monitor(e):
        """Inicia ou para o monitoramento em tempo real"""
        nonlocal monitor_thread, monitor_running
        
        if monitor_running:
            monitor_running = False
            if monitor_thread and monitor_thread.is_alive():
                monitor_thread.join(timeout=1)
            monitor_toggle_button.icon = ft.Icons.PLAY_ARROW
            monitor_toggle_button.text = "Iniciar Monitoramento"
        else:
            monitor_running = True
            monitor_thread = threading.Thread(target=update_monitor_data, daemon=True)
            monitor_thread.start()
            monitor_toggle_button.icon = ft.Icons.STOP
            monitor_toggle_button.text = "Parar Monitoramento"
        
        page.update()

    def termux_ssh_setup(e):
        def fechar_dialog():
            dialog.open = False
            page.update()

        def detectar_arquitetura(COMMANDO):
            """Detecta a arquitetura do dispositivo para baixar o APK correto"""
            try:
                # Obter a arquitetura do processador
                arch_output = COMMANDO._run_adb_shell_command(["uname", "-m"])
                if not arch_output:
                    # Fallback: usar getprop
                    arch_output = COMMANDO._run_adb_shell_command(["getprop", "ro.product.cpu.abi"])
                
                arch = arch_output.strip().lower() if arch_output else "arm64-v8a"
                
                # Mapear arquiteturas para os sufixos do Shizuku
                arch_map = {
                    "arm64": "arm64-v8a",
                    "aarch64": "arm64-v8a", 
                    "arm64-v8a": "arm64-v8a",
                    "arm": "armeabi-v7a",
                    "armeabi-v7a": "armeabi-v7a",
                    "x86_64": "x86_64",
                    "x86": "x86"
                }
                
                for key, value in arch_map.items():
                    if key in arch:
                        return value
                
                return "arm64-v8a"  # padrão mais comum
                
            except Exception as ex:
                print(f"❌ Erro ao detectar arquitetura: {ex}")
                return "arm64-v8a"
        
        def baixar_instalar_termux(COMMANDO):
            try:
                # 1. Detectar arquitetura do dispositivo
                arquitetura = detectar_arquitetura(COMMANDO)
                print(f"📱 Arquitetura detectada: {arquitetura}")
                
                # 2. Obter última versão no GitHub
                url = "https://api.github.com/repos/termux/termux-app/releases/latest"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'application/vnd.github.v3+json'
                }
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                release = response.json()

                # 3. Encontrar o APK correto para a arquitetura
                apk_url = None
                apk_name = None
                
                # Prioridade de busca: universal > arch-specific > qualquer apk
                priority_assets = []
                
                for asset in release["assets"]:
                    asset_name = asset["name"].lower()
                    if asset_name.endswith(".apk"):
                        # Verificar se é universal
                        if "universal" in asset_name:
                            priority_assets.insert(0, asset)  # Máxima prioridade
                        # Verificar se corresponde à arquitetura
                        elif any(arch in asset_name for arch in [arquitetura, "arm64", "aarch64", "armeabi", "x86"]):
                            # Dar prioridade baseada na correspondência exata
                            if arquitetura in asset_name:
                                priority_assets.insert(1, asset)
                            else:
                                priority_assets.append(asset)
                        else:
                            priority_assets.append(asset)  # Baixa prioridade
                
                # Selecionar o melhor APK
                if priority_assets:
                    selected_asset = priority_assets[0]
                    apk_url = selected_asset["browser_download_url"]
                    apk_name = selected_asset["name"]
                else:
                    # Fallback: pegar qualquer APK se não encontrou específico
                    for asset in release["assets"]:
                        if asset["name"].endswith(".apk"):
                            apk_url = asset["browser_download_url"]
                            apk_name = asset["name"]
                            break

                if not apk_url:
                    print("❌ Não foi possível encontrar o APK do Termux na última release.")
                    return False

                print(f"📦 APK selecionado: {apk_name}")
                print(f"🔗 URL: {apk_url}")

                # 4. Baixar o APK
                apk_path = f"termux-{arquitetura}.apk"
                print(f"⬇️ Baixando {apk_name} ...")
                
                r = requests.get(apk_url, headers=headers, stream=True)
                r.raise_for_status()
                
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0
                
                with open(apk_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                print(f"📥 Progresso: {percent:.1f}% ({downloaded}/{total_size} bytes)", end='\r')

                print("\n✅ Download concluído!")

                # 5. Instalar no dispositivo
                print("📲 Instalando Termux no dispositivo...")
                
                adb_path = localizar_adb()[0]
                install_result = subprocess.run([
                    adb_path, "install", "-r", "-g", apk_path
                ], capture_output=True, text=True, timeout=120)
                
                if install_result.returncode == 0:
                    print("✅ Instalação do Termux concluída com sucesso!")
                else:
                    print(f"⚠️ Código de saída: {install_result.returncode}")
                    if install_result.stdout:
                        print(f"Saída: {install_result.stdout}")
                    if install_result.stderr:
                        print(f"Erros: {install_result.stderr}")

                # 6. Limpar arquivo temporário
                if os.path.exists(apk_path):
                    os.remove(apk_path)
                    print("🧹 Arquivo temporário removido")
                    
                return install_result.returncode == 0

            except requests.exceptions.RequestException as ex:
                print(f"❌ Erro de rede ao baixar Termux: {ex}")
                return False
            except subprocess.TimeoutExpired:
                print("❌ Timeout na instalação do APK")
                return False
            except Exception as ex:
                print(f"❌ Erro ao baixar/instalar Termux: {ex}")
                return False

        adb_path = localizar_adb()
        if not adb_path:
            print("❌ ADB não encontrado")
            return

        COMMANDO = DeviceMonitor(adb_path[0])

        def verificar_termux_instalado():
            """Verifica se o Termux está instalado"""
            try:
                result = COMMANDO._run_adb_shell_command(["pm", "list", "packages", "com.termux"])
                return result and "com.termux" in result
            except Exception as ex:
                print(f"❌ Erro ao verificar Termux: {ex}")
                return False
            
        def inserir_comandos(e,senha):
            try:
                senha_ssh = senha.value.strip()
                print("1. Iniciando instalação do OpenSSH no Termux...")
                
                # Digita 'pkg install openssh' e simula o Enter (66)
                COMMANDO._run_adb_shell_command(["input", "text", "pkg%sinstall%sopenssh"])
                COMMANDO._run_adb_shell_command(["input", "keyevent", "66"])
                
                time.sleep(10) # Tempo para processar o comando e pedir confirmação
                
                # Digita 'y' (Sim) e simula o Enter (66)
                COMMANDO._run_adb_shell_command(["input", "text", "y"])
                COMMANDO._run_adb_shell_command(["input", "keyevent", "66"])
                
                time.sleep(10) # Tempo para a instalação ser concluída

                # ----------------------------------------------------
                # Parte 2: Envio e Preparação do Script
                # ----------------------------------------------------
                print("2. Enviando e preparando o script...")
                
                # Adb push (envia o arquivo local 'config_ssh_auto.sh' para o Termux)
                COMMANDO._run_adb_shell_command(["push", "config_ssh_auto.sh", "/data/data/com.termux/files/home/"]) 
                
                # Adb shell (Define permissão de execução)
                # Nota: Usamos "shell" como primeiro argumento para garantir que o comando seja executado DENTRO do Android.
                COMMANDO._run_adb_shell_command(["shell", "chmod", "+x", "/data/data/com.termux/files/home/config_ssh_auto.sh"]) 
                
                # ----------------------------------------------------
                # Parte 3: Execução do Script NÃO INTERATIVO COM ARGUMENTOS
                # ----------------------------------------------------
                print(f"3. Executando script de configuração para usuário: {"termux"}...")

                # Adb shell: Executa o script, passando o usuário ($1) e a senha ($2) como argumentos
                comando_execucao = [
                    "shell", 
                    "/data/data/com.termux/files/home/config_ssh_auto.sh", 
                    "termux", 
                    senha_ssh
                ]
                
                # O script rodará, usará os argumentos e não pedirá mais input.
                COMMANDO._run_adb_shell_command(comando_execucao)
                
                print("✅ Configuração finalizada com sucesso!")

            except Exception as ex:
                print(f"❌ Erro na automação ADB: {ex}")

        def verificar_e_configurar(e):
            try:
                # Verificar se Termux está instalado
                if not verificar_termux_instalado():
                    print("❌ Termux não está instalado. Baixando...")
                    if not baixar_instalar_termux(COMMANDO):
                        aviso_erro = ft.AlertDialog(
                            modal=True,
                            title=ft.Text("Erro"),
                            content=ft.Text("Falha ao instalar Termux automaticamente."),
                            actions=[ft.FilledButton("Ok", on_click=lambda _: setattr(aviso_erro, 'open', False) or page.update())]
                        )
                        page.overlay.append(aviso_erro)
                        aviso_erro.open = True
                        page.update()
                        return
                else:
                    # Descobrir a activity principal
                    activity_output = COMMANDO._run_adb_shell_command([
                        "cmd", "package", "resolve-activity", "--brief", "com.termux"
                    ])
                    activity = activity_output.strip().splitlines()[-1]
                    if activity:
                        result = COMMANDO._run_adb_shell_command([
                            "am", "start", "-n", activity
                        ])
                        if result:
                            print("Sucesso ao iniciar o Termux")
                            senha_input = ft.TextField(
                                label="Senha SSH", 
                                password=True,
                                hint_text="Digite uma senha para o usuário 'termux'"
                            )
                            
                            submit_btn = ft.FilledButton("Ativar SSH",on_click=lambda _: inserir_comandos(_,senha_input))

                            aviso = ft.AlertDialog(
                                modal=True,
                                title=ft.Text("Configuração SSH"),
                                content=ft.Column([
                                    ft.Text("O Termux usará o usuário: termux"),
                                    ft.Text("Digite uma senha para SSH:"),
                                    senha_input
                                ], tight=True),
                                actions=[submit_btn]
                            )
                            page.overlay.append(aviso)
                            aviso.open = True
                            page.update()

            except Exception as ex:
                print(f"❌ Erro: {ex}")
                fechar_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Ativar SSH no Termux"),
            content=ft.Text("Isso criará um arquivo .sh localmente, enviará para o dispositivo e executará no Termux."),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: setattr(dialog, 'open', False) or page.update()),
                ft.FilledButton("Continuar", on_click=verificar_e_configurar),
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )

        page.overlay.append(dialog)
        dialog.open = True
        page.update()
    # --- Montagem da UI ---
    loading_container = ft.Container(content=ft.Column([ft.ProgressRing(width=32, height=32, stroke_width=3, color=theme_colors["primary"]), ft.Text("Configurando ambiente ADB...", color=theme_colors["text"], size=14)], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15), alignment=ft.alignment.center, expand=True)
    def create_device_info_row(icon, text_control): return ft.Row([ft.Icon(icon, color=theme_colors["subtext"], size=16), text_control], spacing=10)
    power_controls = ft.Row(controls=[ft.IconButton(icon=ft.Icons.POWER_SETTINGS_NEW, on_click=handle_power_off, tooltip="Desligar Dispositivo", icon_color=theme_colors["subtext"], style=ft.ButtonStyle(shape=ft.CircleBorder())), ft.IconButton(icon=ft.Icons.RESTART_ALT, on_click=handle_reboot, tooltip="Reiniciar Dispositivo", icon_color=theme_colors["subtext"], style=ft.ButtonStyle(shape=ft.CircleBorder())), ft.IconButton(icon=ft.Icons.TERMINAL, on_click=handle_reboot_fastboot, tooltip="Reiniciar em Modo Fastboot", icon_color=theme_colors["subtext"], style=ft.ButtonStyle(shape=ft.CircleBorder()))], alignment=ft.MainAxisAlignment.CENTER)
    wifi_connect_button = ft.FilledTonalButton("Conectar via Wi-Fi", icon=ft.Icons.WIFI, on_click=conectar_wifi_automatico, width=210)
    espelhar_tela_button = ft.FilledTonalButton("Espelhar Tela", on_click=executar_espelhamento, icon=ft.Icons.SCREEN_LOCK_PORTRAIT, width=210)
    sidebar = ft.Container(width=250, padding=20, border_radius=12, bgcolor=theme_colors["surface"], content=ft.Column(controls=[
        ft.Row([ft.Icon(ft.Icons.ANDROID, color=theme_colors["primary"], size=24), ft.Text("ADB Control", size=16, weight=ft.FontWeight.BOLD)], spacing=10), ft.Divider(height=15), ft.Text("Dispositivo", weight=ft.FontWeight.BOLD, color=theme_colors["subtext"]), create_device_info_row(ft.Icons.BADGE_OUTLINED, device_name), create_device_info_row(ft.Icons.PHONE_ANDROID_OUTLINED, device_model), create_device_info_row(ft.Icons.TAG, device_android), create_device_info_row(ft.Icons.BUSINESS_OUTLINED, device_manufacturer), ft.Divider(height=15), ft.Row([status_indicator, device_status], spacing=10), ft.Divider(height=10), ft.Text("Controles", weight=ft.FontWeight.BOLD, color=theme_colors["subtext"]), power_controls, ft.Column(controls=[wifi_connect_button, espelhar_tela_button, ft.FilledTonalButton("Reconectar", icon=ft.Icons.REFRESH, on_click=atualizar_info, width=210)], expand=True, alignment=ft.MainAxisAlignment.END, spacing=5)], spacing=8))
    
    apps_list = ft.ListView(expand=True, spacing=5, padding=ft.padding.only(top=10, right=5))
    file_picker = ft.FilePicker(on_result=on_apk_picked); page.overlay.append(file_picker)
    installer_progress_ring = ft.ProgressRing(visible=False, width=32, height=32); installer_icon = ft.Icon(ft.Icons.UPLOAD_FILE_ROUNDED, size=48, color=theme_colors["subtext"]); installer_text = ft.Text("Arraste e solte o APK aqui ou clique para selecionar", color=theme_colors["subtext"], text_align=ft.TextAlign.CENTER)
    apk_installer_view = ft.Container(content=ft.Column([ft.DragTarget(group="apk", on_accept=on_drag_accept, on_will_accept=on_drag_will_accept, on_leave=on_drag_leave, content=ft.Container(content=ft.Stack([installer_icon, installer_progress_ring], expand=True), alignment=ft.alignment.center, border=ft.border.all(1, theme_colors["subtext"]), border_radius=12, padding=20, expand=True, on_click=lambda _: file_picker.pick_files(allow_multiple=False, allowed_extensions=["apk"]))), installer_text, ft.FilledButton("Voltar para a lista", icon=ft.Icons.ARROW_BACK, on_click=hide_apk_installer_view, style=ft.ButtonStyle(bgcolor=theme_colors["surface"],color=theme_colors["text"]))], expand=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10), visible=False, expand=True)
    campo_pesquisa = ft.TextField(hint_text="Pesquisar por nome ou pacote...", on_change=filtrar_apps, border_color=theme_colors["surface"], focused_border_color=theme_colors["primary"], border_radius=8, prefix_icon=ft.Icons.SEARCH, dense=True, content_padding=ft.padding.symmetric(vertical=10), expand=True)
    Paramentro_de_Carregamento = ft.Switch(label="Apps de Terceiros", value=False)
    menu_opcoes_apps = ft.PopupMenuButton(items=[ft.PopupMenuItem(text="Instalação de APK", icon=ft.Icons.INSTALL_MOBILE, on_click=show_apk_installer_view),ft.PopupMenuItem(text="Ativar Shinzuku", icon=ft.Icons.ANDROID, on_click=shizuku_active),ft.PopupMenuItem(text="Iniciar SSH Atraves do Termux", on_click=termux_ssh_setup,icon=ft.Icons.WIFI)], icon=ft.Icons.MORE_VERT)
    apps_content = ft.Column(controls=[ft.Row([ft.Text("Gerenciador de Aplicativos", size=18, weight=ft.FontWeight.BOLD, expand=True), ft.FilledButton("Carregar Apps", icon=ft.Icons.APPS, on_click=carregar_apps_otimizado, style=ft.ButtonStyle(bgcolor=theme_colors["primary"], color=theme_colors["on_primary"]))], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), ft.Row([campo_pesquisa,Paramentro_de_Carregamento, menu_opcoes_apps], vertical_alignment=ft.CrossAxisAlignment.CENTER), ft.Divider(height=5, color="transparent"), ft.Stack([apps_list, apk_installer_view], expand=True)], expand=True)

    logcat_list = ft.ListView(expand=True, spacing=2, auto_scroll=True)
    logcat_toggle_button = ft.FilledButton("Iniciar", icon=ft.Icons.PLAY_ARROW, on_click=start_stop_logcat)
    logcat_content = ft.Column(controls=[ft.Row([logcat_toggle_button, ft.FilledButton("Limpar", icon=ft.Icons.CLEAR_ALL, on_click=clear_logcat)], spacing=10), logcat_list], expand=True)
    
    def create_setting_control(label, min_val, max_val, initial_val, divisions):
        text_field = ft.TextField(value=str(initial_val), width=80, text_align=ft.TextAlign.CENTER, dense=True, border_color=theme_colors["surface"]); slider = ft.Slider(min=min_val, max=max_val, value=initial_val, divisions=divisions, label="{value}")
        def sync_slider_to_text(e): text_field.value = str(int(e.control.value)); page.update()
        def sync_text_to_slider(e):
            try: value = int(e.control.value); slider.value = max(slider.min, min(slider.max, value)); text_field.value = str(int(slider.value))
            except (ValueError, TypeError): text_field.value = str(int(slider.value))
            page.update()
        slider.on_change, text_field.on_submit, text_field.on_blur = sync_slider_to_text, sync_text_to_slider, sync_text_to_slider
        return text_field, slider, ft.Column([ft.Text(label, size=14), ft.Row([text_field, slider], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)], spacing=5)
    width_field, width_slider, width_control = create_setting_control("Largura (Width)", 720, 1920, 1080, 120)
    height_field, height_slider, height_control = create_setting_control("Altura (Height)", 1280, 4096, 1920, 280)
    dpi_field, dpi_slider, dpi_control = create_setting_control("DPI (Densidade)", 120, 640, 320, 52)
    refresh_field, refresh_slider, refresh_control = create_setting_control("Taxa de Atualização (Hz)", 30, 240, 60, 21)
    current_resolution, current_dpi, current_refresh_rate = ft.Text("...", size=12, color=theme_colors["subtext"]), ft.Text("...", size=12, color=theme_colors["subtext"]), ft.Text("...", size=12, color=theme_colors["subtext"])
    config_content = ft.Column(controls=[ft.Row([ft.Text("Configurações de Display", size=18, weight=ft.FontWeight.BOLD), ft.Row([ft.FilledTonalButton("Atualizar", icon=ft.Icons.REFRESH, on_click=carregar_configuracoes_atuais), ft.FilledTonalButton("Resetar Padrão", icon=ft.Icons.RESTART_ALT, on_click=resetar_configuracoes, style=ft.ButtonStyle(color=theme_colors["warning"]))])], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), ft.Container(padding=15, border_radius=8, bgcolor=theme_colors["surface"], content=ft.Column([ft.Text("Status Atual", size=14, weight=ft.FontWeight.BOLD), ft.Divider(height=5), ft.Row([ft.Text("Resolução:", weight=ft.FontWeight.BOLD, color=theme_colors["subtext"]), current_resolution]), ft.Row([ft.Text("DPI:", weight=ft.FontWeight.BOLD, color=theme_colors["subtext"]), current_dpi]), ft.Row([ft.Text("Taxa de Atualização:", weight=ft.FontWeight.BOLD, color=theme_colors["subtext"]), current_refresh_rate])], spacing=5)), ft.Container(padding=15, border_radius=8, bgcolor=theme_colors["surface"], content=ft.Column([width_control, height_control], spacing=10)), ft.Container(padding=15, border_radius=8, bgcolor=theme_colors["surface"], content=dpi_control), ft.Container(padding=15, border_radius=8, bgcolor=theme_colors["surface"], content=refresh_control), ft.Row([ft.FilledButton("Aplicar Configurações", icon=ft.Icons.SAVE, on_click=aplicar_configuracoes, style=ft.ButtonStyle(bgcolor=theme_colors["success"], color=theme_colors["on_primary"]))], alignment=ft.MainAxisAlignment.END)], spacing=15, scroll=ft.ScrollMode.ADAPTIVE, expand=True)
    info_content_area = ft.Column(scroll=ft.ScrollMode.ADAPTIVE, expand=True, spacing=15)
    def create_info_card(title, data_dict):
        rows = [ft.Row([ft.Text(f"{key}:", weight=ft.FontWeight.BOLD, color=theme_colors["subtext"]), ft.Text(value, selectable=True)]) for key, value in data_dict.items() if value and value != "N/A"]
        if not rows: return None
        return ft.Container(padding=15, border_radius=8, bgcolor=theme_colors["surface"], content=ft.Column([ft.Text(title, size=16, weight=ft.FontWeight.BOLD), ft.Divider(height=5), *rows], spacing=8))
    info_page_content = ft.Column(controls=[ft.Row([ft.Text("Informações do Dispositivo", size=18, weight=ft.FontWeight.BOLD), ft.FilledTonalButton("Atualizar", icon=ft.Icons.REFRESH, on_click=load_device_info)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), ft.Divider(height=10, color="transparent"), info_content_area], expand=True)

    

    # --- UI PARA A NOVA ABA DE MONITORAMENTO CORRIGIDA ---
    cpu_value_text = ft.Text("0%", size=16, weight=ft.FontWeight.BOLD, color=theme_colors["primary"])
    ram_value_text = ft.Text("0%", size=16, weight=ft.FontWeight.BOLD, color=theme_colors["success"])
    storage_value_text = ft.Text("0%", size=16, weight=ft.FontWeight.BOLD, color=theme_colors["warning"])
    battery_value_text = ft.Text("0%", size=16, weight=ft.FontWeight.BOLD, color=theme_colors["error"])
    
    monitor_toggle_button = ft.FilledButton("Iniciar Monitoramento", icon=ft.Icons.PLAY_ARROW, on_click=start_stop_monitor)
    
    # Criar os gráficos iniciais
    cpu_chart_ref = create_chart(cpu_data, theme_colors["primary"], "CPU")
    ram_chart_ref = create_chart(ram_data, theme_colors["success"], "RAM")
    storage_chart_ref = create_chart(storage_data, theme_colors["warning"], "Armazenamento")
    battery_chart_ref = create_chart(battery_data, theme_colors["error"], "Bateria", 100)
    
    monitor_content = ft.Column(
        controls=[
            ft.Row([
                ft.Text("Monitoramento em Tempo Real", size=18, weight=ft.FontWeight.BOLD, expand=True),
                monitor_toggle_button
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(height=20),
            ft.Row([
                ft.Container(
                    content=ft.Column([
                        ft.Row([ft.Icon(ft.Icons.MEMORY, color=theme_colors["primary"]), ft.Text("CPU", size=16), cpu_value_text]),
                        cpu_chart_ref
                    ], spacing=10),
                    expand=True
                ),
                ft.Container(
                    content=ft.Column([
                        ft.Row([ft.Icon(ft.Icons.STORAGE, color=theme_colors["success"]), ft.Text("RAM", size=16), ram_value_text]),
                        ram_chart_ref
                    ], spacing=10),
                    expand=True
                )
            ], spacing=15),
            ft.Divider(height=15),
            ft.Row([
                ft.Container(
                    content=ft.Column([
                        ft.Row([ft.Icon(ft.Icons.SD_CARD, color=theme_colors["warning"]), ft.Text("Armazenamento", size=16), storage_value_text]),
                        storage_chart_ref
                    ], spacing=10),
                    expand=True
                ),
                ft.Container(
                    content=ft.Column([
                        ft.Row([ft.Icon(ft.Icons.BATTERY_STD, color=theme_colors["error"]), ft.Text("Bateria", size=16), battery_value_text]),
                        battery_chart_ref
                    ], spacing=10),
                    expand=True
                )
            ], spacing=15),
            ft.Divider(height=10),
            ft.Text("Os gráficos mostram a utilização dos recursos nos últimos 2 minutos", size=12, color=theme_colors["subtext"], text_align=ft.TextAlign.CENTER)
        ],
        expand=True,
        scroll=ft.ScrollMode.ADAPTIVE
    )

    # Adicione estas funções para a aba de configurações
    def toggle_tema(e):
        """Alterna entre tema claro e escuro"""
        if page.theme_mode == ft.ThemeMode.DARK:
            page.theme_mode = ft.ThemeMode.LIGHT
            # Atualizar cores para tema claro
            atualizar_cores_tema(ft.ThemeMode.LIGHT)
            toggle_tema_button.text = "Modo Escuro"
            toggle_tema_button.icon = ft.Icons.DARK_MODE
        else:
            page.theme_mode = ft.ThemeMode.DARK
            # Atualizar cores para tema escuro
            atualizar_cores_tema(ft.ThemeMode.DARK)
            toggle_tema_button.text = "Modo Claro"
            toggle_tema_button.icon = ft.Icons.LIGHT_MODE
        page.update()

    def atualizar_cores_tema(modo):
        """Atualiza as cores baseado no tema selecionado"""
        global theme_colors
        
        if modo == ft.ThemeMode.LIGHT:
            theme_colors = {
                "background": "#f5f5f5",
                "surface": "#ffffff", 
                "primary": "#1976d2",
                "on_primary": "#ffffff",
                "text": "#333333",
                "subtext": "#666666",
                "success": "#388e3c",
                "error": "#d32f2f",
                "warning": "#f57c00"
            }
        else:
            theme_colors = {
                "background": "#1e1e2e",
                "surface": "#313244", 
                "primary": "#89b4fa",
                "on_primary": "#11111b",
                "text": "#cdd6f4",
                "subtext": "#a6adc8",
                "success": "#a6e3a1",
                "error": "#f38ba8",
                "warning": "#f9e2af"
            }
        
        # Atualizar cores da página
        page.bgcolor = theme_colors["background"]
        
        # Atualizar sidebar
        sidebar.bgcolor = theme_colors["surface"]
        
        # Você pode adicionar mais atualizações de cores aqui conforme necessário

    # Crie o conteúdo da aba de configurações
    def criar_aba_configuracoes():
        return ft.Container(
            padding=20,
            content=ft.Column([
                ft.Text("Configurações", size=24, weight=ft.FontWeight.BOLD),
                ft.Divider(height=20),
                
                ft.Container(
                    padding=15,
                    border_radius=8,
                    bgcolor=theme_colors["surface"],
                    content=ft.Column([
                        ft.Text("Aparência", size=18, weight=ft.FontWeight.BOLD),
                        ft.Divider(height=10),
                        ft.Row([
                            ft.Icon(ft.Icons.PALETTE, color=theme_colors["primary"]),
                            ft.Text("Tema da Interface", expand=True),
                            toggle_tema_button
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                    ], spacing=10)
                ),
                
                ft.Container(
                    padding=15,
                    border_radius=8,
                    bgcolor=theme_colors["surface"],
                    content=ft.Column([
                        ft.Text("Créditos", size=18, weight=ft.FontWeight.BOLD),
                        ft.Divider(height=10),
                        
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.CODE, color=theme_colors["primary"]),
                            title=ft.Text("Criador do APP"),
                            subtitle=ft.Text("ADB Controller"),
                            trailing=ft.IconButton(
                                icon=ft.Icons.OPEN_IN_NEW,
                                on_click=lambda _: page.launch_url("https://github.com/ElyahuMendesdaSilva")
                            )
                        ),
                        
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.ANDROID, color=theme_colors["success"]),
                            title=ft.Text("scrcpy - Screen Copy"),
                            subtitle=ft.Text("Genymobile"),
                            trailing=ft.IconButton(
                                icon=ft.Icons.OPEN_IN_NEW,
                                on_click=lambda _: page.launch_url("https://github.com/Genymobile/scrcpy")
                            )
                        ),
                        
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.LAPTOP, color=theme_colors["warning"]),
                            title=ft.Text("Flet Framework"),
                            subtitle=ft.Text("Framework Python para UI"),
                            trailing=ft.IconButton(
                                icon=ft.Icons.OPEN_IN_NEW,
                                on_click=lambda _: page.launch_url("https://flet.dev")
                            )
                        )
                    ], spacing=5)
                ),
                
                ft.Container(
                    padding=15,
                    border_radius=8,
                    bgcolor=theme_colors["surface"],
                    content=ft.Column([
                        ft.Text("Informações do Sistema", size=18, weight=ft.FontWeight.BOLD),
                        ft.Divider(height=10),
                        
                        ft.Row([
                            ft.Text("Versão do Python:", weight=ft.FontWeight.BOLD),
                            ft.Text(platform.python_version())
                        ]),
                        
                        ft.Row([
                            ft.Text("Sistema Operacional:", weight=ft.FontWeight.BOLD),
                            ft.Text(f"{platform.system()} {platform.release()}")
                        ]),
                        
                        ft.Row([
                            ft.Text("Versão do App:", weight=ft.FontWeight.BOLD),
                            ft.Text("1.0.0")
                        ])
                    ], spacing=8)
                )
            ], scroll=ft.ScrollMode.ADAPTIVE),
            expand=True
        )

    # Adicione o botão de toggle do tema (coloque isso na seção de variáveis globais)
    toggle_tema_button = ft.FilledTonalButton(
        "Modo Claro" if page.theme_mode == ft.ThemeMode.DARK else "Modo Escuro",
        icon=ft.Icons.LIGHT_MODE if page.theme_mode == ft.ThemeMode.DARK else ft.Icons.DARK_MODE,
        on_click=toggle_tema
    )
    # Atualize a definição das tabs para incluir a nova aba de Configurações
    tabs = ft.Tabs(
        selected_index=0, animation_duration=300,
        tabs=[
            ft.Tab(text=" Apps", icon=ft.Icons.APPS, content=ft.Container(apps_content, padding=20, expand=True)),
            ft.Tab(text=" Tela", icon=ft.Icons.TUNE, content=ft.Container(config_content, padding=20, expand=True)),
            ft.Tab(text=" Info", icon=ft.Icons.INFO_OUTLINE, content=ft.Container(info_page_content, padding=20, expand=True)),
            ft.Tab(text=" Monitor", icon=ft.Icons.MONITOR_HEART, content=ft.Container(monitor_content, padding=20, expand=True)),
            ft.Tab(text=" Logcat", icon=ft.Icons.DESCRIPTION, content=ft.Container(logcat_content, padding=20, expand=True)),
            ft.Tab(text=" Config", icon=ft.Icons.SETTINGS, content=criar_aba_configuracoes()),
        ], expand=True, indicator_color=theme_colors["primary"], label_color=theme_colors["primary"]
    )
    
    page.add(loading_container)
    if inicializar_adb_completo():
        page.clean()
        page.add(ft.Row([sidebar, ft.VerticalDivider(width=1, color=theme_colors["surface"]), tabs], expand=True, spacing=20))
        atualizar_info()
        carregar_configuracoes_atuais()
        load_device_info()

if __name__ == "__main__":
    ft.app(target=main, upload_dir="uploads")