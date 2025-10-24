# backend.py
import json
import pyperclip
import tarfile
import re
import threading
import time
import os
import platform
import requests
import shutil
import subprocess
import zipfile
import base64
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

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
            archive_path = self.base_dir / Path(url).name
            with requests.get(url, stream=True) as r, open(archive_path, 'wb') as f:
                shutil.copyfileobj(r.raw, f)

            extracted_dir = self.base_dir / "scrcpy_extracted"
            if extracted_dir.exists():
                shutil.rmtree(extracted_dir)
            extracted_dir.mkdir(exist_ok=True)

            if archive_path.suffix == ".zip":
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(extracted_dir)
            elif archive_path.suffixes[-2:] == [".tar", ".gz"]:
                with tarfile.open(archive_path, "r:gz") as tar_ref:
                    tar_ref.extractall(extracted_dir)
            else:
                return False, f"Formato de arquivo não suportado: {archive_path}"

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
        if package_name in self.memory_cache: 
            return self.memory_cache[package_name]
        cache_file = self.icon_cache_dir / f"{package_name}.png"
        if cache_file.exists():
            try:
                with open(cache_file, "rb") as f: 
                    icon_data = base64.b64encode(f.read()).decode()
                icon_url = f"data:image/png;base64,{icon_data}"
                self.memory_cache[package_name] = icon_url
                return icon_url
            except Exception as e: 
                print(f"Erro ao ler cache do ícone: {e}")
        
        icon_bytes = self._extract_icon_from_apk(package_name)

        if icon_bytes:
            try:
                with open(cache_file, "wb") as f: 
                    f.write(icon_bytes)
                icon_data = base64.b64encode(icon_bytes).decode()
                icon_url = f"data:image/png;base64,{icon_data}"
                self.memory_cache[package_name] = icon_url
                return icon_url
            except Exception as e: 
                print(f"Erro ao salvar/converter ícone: {e}")
        
        return self.default_icon_b64

    def _extract_icon_from_apk(self, package_name):
        temp_apk_path = None
        try:
            cmd_path = [self.adb_path, "shell", "pm", "path", package_name]
            result = subprocess.run(cmd_path, capture_output=True, text=True, timeout=10)
            if result.returncode != 0 or not result.stdout.strip(): 
                return None
            
            apk_path_on_device = result.stdout.strip().replace("package:", "")
            temp_apk_path = self.icon_cache_dir / f"{package_name}_temp.apk"
            cmd_pull = [self.adb_path, "pull", apk_path_on_device, str(temp_apk_path)]
            subprocess.run(cmd_pull, capture_output=True, timeout=60)

            if not temp_apk_path.exists(): 
                return None

            with zipfile.ZipFile(temp_apk_path, 'r') as apk:
                filenames = apk.namelist()
                search_priority = [
                    'res/mipmap-xxxhdpi-v4/ic_launcher.png', 
                    'res/mipmap-xxhdpi-v4/ic_launcher.png',
                    'res/mipmap-xhdpi-v4/ic_launcher.png', 
                    'res/mipmap-hdpi-v4/ic_launcher.png',
                    'res/mipmap-mdpi-v4/ic_launcher.png', 
                    'res/mipmap-xxxhdpi/ic_launcher.png',
                    'res/mipmap-xxhdpi/ic_launcher.png', 
                    'res/mipmap-xhdpi/ic_launcher.png',
                    'res/mipmap-hdpi/ic_launcher.png', 
                    'res/mipmap-mdpi/ic_launcher.png',
                    'res/drawable-xxhdpi-v4/icon.png', 
                    'res/drawable-xxhdpi/icon.png',
                ]
                for path in search_priority:
                    if path in filenames:
                        with apk.open(path) as icon_file: 
                            return icon_file.read()
                
                possible_icons = [f for f in filenames if 'ic_launcher.png' in f]
                if possible_icons:
                    sorted_icons = sorted(possible_icons, key=lambda p: ('xxxhdpi' in p, 'xxhdpi' in p, 'xhdpi' in p), reverse=True)
                    with apk.open(sorted_icons[0]) as icon_file: 
                        return icon_file.read()
            return None
        except Exception as e:
            print(f"Falha ao extrair ícone para {package_name}: {e}")
            return None
        finally:
            if temp_apk_path and temp_apk_path.exists(): 
                temp_apk_path.unlink()

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
                    if result: 
                        results.append(result)
                except Exception as e:
                    pkg = future_to_package[future]
                    print(f"Erro no future para {pkg}: {e}")
                    results.append({"name": pkg, "package": pkg, "version": "N/A"})
        return results

    def get_single_app_info_no_icon(self, package_name):
        app_name = package_name
        version = "N/A"
        try:
            dump_output = subprocess.check_output(
                [self.adb_path, "shell", "pm", "dump", package_name], 
                text=True, stderr=subprocess.DEVNULL, errors="ignore", timeout=10
            )
            label_re = re.compile(r"label=(.+)")
            for line in dump_output.splitlines():
                match = label_re.search(line)
                if match:
                    found_name = match.group(1).strip()
                    if found_name and found_name != "null":
                        app_name = found_name
                        break
            dumpsys_output = subprocess.check_output(
                [self.adb_path, "shell", "dumpsys", "package", package_name], 
                text=True, stderr=subprocess.DEVNULL, errors="ignore", timeout=10
            )
            version_re = re.compile(r"versionName=(.+)")
            for line in dumpsys_output.splitlines():
                match = version_re.search(line)
                if match:
                    version = match.group(1).strip()
                    break
        except Exception: 
            pass
        return {"name": app_name, "package": package_name, "version": version}

class ConfigManager:
    def __init__(self, adb_path): 
        self.adb_path = adb_path
    
    def _run_adb_command(self, command, timeout=10):
        try:
            result = subprocess.run(
                [self.adb_path, "shell"] + command, 
                capture_output=True, text=True, timeout=timeout, errors='ignore'
            )
            if result.returncode != 0: 
                print(f"Erro no comando 'adb shell {' '.join(command)}': {result.stderr.strip()}")
                return None
            return result.stdout.strip()
        except Exception as e: 
            print(f"Exceção ao executar comando: {e}")
            return None
    
    def get_current_display_settings(self):
        size_output = self._run_adb_command(["wm", "size"])
        resolution = size_output.replace("Physical size: ", "") if size_output else "N/A"
        
        density_output = self._run_adb_command(["wm", "density"])
        dpi = density_output.replace("Physical density: ", "") if density_output else "N/A"
        
        refresh_rate = "N/A"
        display_info = self._run_adb_command(["dumpsys", "display"])
        if display_info:
            match = re.search(r'mRefreshRate=([\d.]+)', display_info)
            if match: 
                refresh_rate = match.group(1)
        
        return {"resolution": resolution, "dpi": dpi, "refresh_rate": refresh_rate}
    
    def set_display_settings(self, width, height, dpi, refresh_rate):
        all_success = True
        if width and height:
            if self._run_adb_command(["wm", "size", f"{width}x{height}"]) is None: 
                all_success = False
        if dpi:
            if self._run_adb_command(["wm", "density", str(dpi)]) is None: 
                all_success = False
        if refresh_rate:
            if self._run_adb_command(["settings", "put", "system", "peak_refresh_rate", str(refresh_rate)]) is None: 
                all_success = False
            if self._run_adb_command(["settings", "put", "system", "min_refresh_rate", str(refresh_rate)]) is None: 
                all_success = False
        return all_success
    
    def reset_display_settings(self):
        commands = [
            ["wm", "size", "reset"], 
            ["wm", "density", "reset"], 
            ["settings", "delete", "system", "peak_refresh_rate"], 
            ["settings", "delete", "system", "min_refresh_rate"]
        ]
        results = [self._run_adb_command(cmd) is not None for cmd in commands]
        return all(results)
    
    def get_full_device_info(self):
        all_props_raw = self._run_adb_command(["getprop"], timeout=15)
        if not all_props_raw: 
            return None
        
        props = {}
        for line in all_props_raw.splitlines():
            match = re.match(r'\[(.*?)\]: \[(.*?)\]', line)
            if match:
                props[match.groups()[0]] = match.groups()[1]
        
        def get_prop(key, default="N/A"): 
            return props.get(key, default)
        
        def format_boolean_prop(key, true_val="Sim", false_val="Não"):
            value = get_prop(key)
            if value == "true" or value == "1": 
                return true_val
            if value == "false" or value == "0": 
                return false_val
            return "N/A"
        
        bootloader_state = get_prop("ro.boot.vbmeta.device_state")
        if bootloader_state == "N/A": 
            bootloader_state = get_prop("ro.boot.verifiedbootstate", "N/A")
        
        if bootloader_state == "locked": 
            bootloader_status = "Bloqueado"
        elif bootloader_state == "unlocked": 
            bootloader_status = "Desbloqueado"
        else: 
            bootloader_status = "N/A"
        
        oem_allowed_raw = self._run_adb_command(["settings", "get", "global", "oem_unlocking"])
        if oem_allowed_raw == "1": 
            oem_allowed = "Sim"
        elif oem_allowed_raw == "0": 
            oem_allowed = "Não"
        else: 
            oem_allowed = "Desconhecido"
        
        battery_info = {}
        battery_dump = self._run_adb_command(["dumpsys", "battery"])
        if battery_dump:
            for line in battery_dump.splitlines():
                line = line.strip()
                if "level:" in line: 
                    battery_info["Nível"] = f"{line.split(': ')[1]}%"
                elif "status:" in line: 
                    status_codes = ["?", "Desconhecido", "Carregando", "Descarregando", "Não está carregando", "Cheia"]
                    try:
                        status_idx = int(line.split(': ')[1])
                        battery_info["Status"] = status_codes[status_idx] if status_idx < len(status_codes) else "Desconhecido"
                    except:
                        battery_info["Status"] = "Desconhecido"
                elif "health:" in line: 
                    health_codes = ["?", "Desconhecida", "Boa", "Superaquecida", "Morta", "Sobretensão", "Falha não especificada", "Fria"]
                    try:
                        health_idx = int(line.split(': ')[1])
                        battery_info["Saúde"] = health_codes[health_idx] if health_idx < len(health_codes) else "Desconhecida"
                    except:
                        battery_info["Saúde"] = "Desconhecida"
                elif "temperature:" in line: 
                    try:
                        temp = int(line.split(': ')[1]) / 10
                        battery_info["Temperatura"] = f"{temp}°C"
                    except:
                        battery_info["Temperatura"] = "N/A"
                elif "voltage:" in line: 
                    try:
                        voltage = int(line.split(': ')[1]) / 1000
                        battery_info["Voltagem"] = f"{voltage}V"
                    except:
                        battery_info["Voltagem"] = "N/A"
        
        storage_info = {}
        storage_dump = self._run_adb_command(["df", "-h", "/data"])
        if storage_dump and len(storage_dump.splitlines()) > 1:
            parts = storage_dump.splitlines()[1].split()
            if len(parts) >= 5: 
                storage_info["Tamanho Total"] = parts[1]
                storage_info["Usado"] = parts[2]
                storage_info["Disponível"] = parts[3]
                storage_info["Uso%"] = parts[4]
        
        net_info = {}
        net_dump = self._run_adb_command(["ip", "addr", "show", "wlan0"])
        if net_dump:
            ip_match = re.search(r'inet ([\d\.]+)/\d+', net_dump)
            mac_match = re.search(r'link/ether ([\w:]+)', net_dump)
            if ip_match: 
                net_info["Endereço IP"] = ip_match.group(1)
            if mac_match: 
                net_info["Endereço MAC"] = mac_match.group(1)
        
        ram_info_raw = self._run_adb_command(["cat", "/proc/meminfo"])
        match = re.search(r'MemTotal:\s+(\d+)\s+kB', ram_info_raw)
        if match:
            total_kb = int(match.group(1))
            total_gb = total_kb / 1024 / 1024
            ram_total = f"{total_gb:.2f} GB"
        else:
            ram_total = "N/A"
        
        info = {
            "Hardware e SoC": {
                "Modelo": get_prop("ro.product.model"), 
                "Fabricante": get_prop("ro.product.manufacturer"), 
                "Plataforma (Chipset)": get_prop("ro.board.platform"), 
                "Memória RAM Total": ram_total
            },
            "Software e Build": {
                "Versão do Android": get_prop("ro.build.version.release"), 
                "Nível da API (SDK)": get_prop("ro.build.version.sdk"), 
                "ID da Build": get_prop("ro.build.id"), 
                "Patch de Segurança": get_prop("ro.build.version.security_patch")
            },
            "Suporte a GSI & Project Treble": {
                "Project Treble Habilitado": format_boolean_prop("ro.treble.enabled"), 
                "Seamless Updates (Partição A/B)": format_boolean_prop("ro.build.ab_update"), 
                "System-as-Root": format_boolean_prop("ro.build.system_root_image"), 
                "Arquitetura da CPU": get_prop("ro.product.cpu.abi"), 
                "Versão VNDK": get_prop("ro.vndk.version"), 
                "Suporte a Desbloqueio OEM": format_boolean_prop("ro.oem_unlock_supported", "Sim", "Não Suportado"), 
                "Desbloqueio OEM Permitido": oem_allowed, 
                "Status do Bootloader": bootloader_status,
            },
            "Display": self.get_current_display_settings(), 
            "Bateria": battery_info, 
            "Armazenamento (/data)": storage_info, 
            "Rede (Wi-Fi)": net_info,
            "Identificadores": {
                "Número de Série": get_prop("ro.serialno"), 
                "Android ID": self._run_adb_command(["settings", "get", "secure", "android_id"])
            }
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
        if not top_output: 
            return "N/A"
        
        for line in top_output.splitlines():
            if "CPU" in line:
                match = re.search(r'(\d+)% *user.*, *(\d+)% *sys', line)
                if match:
                    user, sys = int(match.group(1)), int(match.group(2))
                    return f"{user + sys}%"
        return "N/A"

    def get_cpu_usage_percentage(self):
        usage_str = self.get_cpu_usage()
        if usage_str == "N/A": 
            return 0
        try:
            return float(usage_str.replace('%', ''))
        except:
            return 0

    def get_ram_usage(self):
        mem_info = self._run_adb_shell_command(["cat", "/proc/meminfo"])
        if not mem_info: 
            return "N/A", "N/A"

        mem_total_match = re.search(r"MemTotal:\s+(\d+)\s+kB", mem_info)
        mem_available_match = re.search(r"MemAvailable:\s+(\d+)\s+kB", mem_info)

        if not mem_total_match or not mem_available_match: 
            return "N/A", "N/A"

        total_kb = int(mem_total_match.group(1))
        available_kb = int(mem_available_match.group(1))
        used_kb = total_kb - available_kb
        usage_percent = (used_kb / total_kb) * 100
        total_gb, used_gb = total_kb / 1048576, used_kb / 1048576
        
        return f"{usage_percent:.1f}%", f"{used_gb:.2f} / {total_gb:.2f} GB"

    def get_ram_usage_percentage(self):
        usage_str, _ = self.get_ram_usage()
        if usage_str == "N/A": 
            return 0
        try:
            return float(usage_str.replace('%', ''))
        except:
            return 0

    def get_storage_usage(self):
        df_output = self._run_adb_shell_command(["df", "-h", "/data"])
        if df_output and len(df_output.splitlines()) > 1:
            parts = df_output.splitlines()[1].split()
            if len(parts) >= 5: 
                return parts[4], f"{parts[2]} / {parts[1]}"
        return "N/A", "N/A"

    def get_storage_usage_percentage(self):
        usage_str, _ = self.get_storage_usage()
        if usage_str == "N/A": 
            return 0
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
        if not output: 
            return []
        apps = []
        start_index = -1
        for i, line in enumerate(output.splitlines()):
            if "PID" in line and "NAME" in line:
                start_index = i + 1
                break
        if start_index == -1: 
            return []

        for line in output.splitlines()[start_index:]:
            parts = line.split()
            if len(parts) >= 2 and "." in parts[-1]:
                pid = parts[0]
                name = parts[-1]
                apps.append({'pid': pid, 'name': name})
        return apps

    def force_stop_app(self, package_name):
        return self._run_adb_shell_command(["am", "force-stop", package_name])

# Funções utilitárias
def executar_comando_adb_simples(adb_path, comando, timeout=30):
    """Executa um comando ADB simples e retorna o resultado"""
    try:
        result = subprocess.run(
            [adb_path] + comando,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors='ignore'
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def criar_script_config_ssh():
    """Cria o script de configuração SSH para o Termux"""
    script_content = """#!/data/data/com.termux/files/usr/bin/bash

# Script de configuração automática do SSH no Termux
# Parâmetros: <usuário> <senha>

USUARIO=$1
SENHA=$2

echo "🔧 Configurando SSH no Termux..."

# Atualizar repositórios
echo "📦 Atualizando repositórios..."
pkg update -y

# Instalar openssh se não estiver instalado
if ! command -v sshd &> /dev/null; then
    echo "📥 Instalando OpenSSH..."
    pkg install openssh -y
fi

# Configurar senha para o usuário
echo "🔐 Configurando senha para usuário $USUARIO..."
echo "$SENHA" | passwd $USUARIO

# Configurar chave SSH se não existir
if [ ! -f ~/.ssh/id_rsa ]; then
    echo "🔑 Gerando chave SSH..."
    ssh-keygen -t rsa -b 2048 -f ~/.ssh/id_rsa -N ""
fi

# Iniciar serviço SSH
echo "🚀 Iniciando serviço SSH..."
sshd

# Mostrar informações de conexão
IP=$(ifconfig wlan0 | grep "inet" | awk '{print $2}' | head -n1)
if [ -z "$IP" ]; then
    IP=$(ifconfig | grep "inet" | grep -v "127.0.0.1" | awk '{print $2}' | head -n1)
fi

echo ""
echo "✅ Configuração concluída!"
echo "📡 Conecte-se usando:"
echo "   ssh $USUARIO@$IP -p 8022"
echo "   Senha: $SENHA"

# Manter o script rodando para mostrar as informações
echo ""
echo "ℹ️  Pressione Ctrl+C para sair"
echo "🔄 O serviço SSH continuará rodando em background"

# Manter o terminal aberto
read -p "Pressione Enter para continuar..."
"""
    
    # Salvar o script localmente
    script_path = "config_ssh_auto.sh"
    try:
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_content)
        
        # Tornar o script executável
        os.chmod(script_path, 0o755)
        return True
    except Exception as e:
        print(f"❌ Erro ao criar script: {e}")
        return False

def processar_script_json(arquivo_json, adb_path):
    """Processa um arquivo JSON com comandos para executar no dispositivo"""
    try:
        with open(arquivo_json, 'r', encoding='utf-8') as f:
            script_data = json.load(f)
        
        resultados = []
        
        # Processar comandos de desinstalação
        if "COMMAND" in script_data and "UNISTALL" in script_data["COMMAND"]:
            for package in script_data["COMMAND"]["UNISTALL"]:
                print(f"🗑️  Desinstalando: {package}")
                success, stdout, stderr = executar_comando_adb_simples(
                    adb_path, ["shell", "pm", "uninstall", "--user", "0", package]
                )
                
                resultados.append({
                    "tipo": "desinstalação",
                    "pacote": package,
                    "sucesso": success,
                    "saida": stdout,
                    "erro": stderr
                })
        
        # Processar outros tipos de comandos
        if "COMMAND" in script_data and "INSTALL" in script_data["COMMAND"]:
            for apk_path in script_data["COMMAND"]["INSTALL"]:
                print(f"📦 Instalando: {apk_path}")
                success, stdout, stderr = executar_comando_adb_simples(
                    adb_path, ["install", "-r", apk_path]
                )
                
                resultados.append({
                    "tipo": "instalação",
                    "arquivo": apk_path,
                    "sucesso": success,
                    "saida": stdout,
                    "erro": stderr
                })
        
        return True, resultados
        
    except Exception as e:
        return False, f"Erro ao processar script: {e}"

def tirar_screenshot(adb_path, arquivo_local="screenshot.png"):
    """Tira um screenshot do dispositivo"""
    try:
        # Tirar screenshot no dispositivo
        success, stdout, stderr = executar_comando_adb_simples(
            adb_path, ["shell", "screencap", "-p", "/sdcard/screenshot.png"]
        )
        
        if success:
            # Copiar para o computador
            success, stdout, stderr = executar_comando_adb_simples(
                adb_path, ["pull", "/sdcard/screenshot.png", arquivo_local]
            )
            
            # Remover do dispositivo
            executar_comando_adb_simples(
                adb_path, ["shell", "rm", "/sdcard/screenshot.png"]
            )
            
            return success
        return False
    except Exception as e:
        print(f"Erro ao tirar screenshot: {e}")
        return False

def backup_app(adb_path, package_name, arquivo_backup="backup.ab"):
    """Faz backup de um aplicativo"""
    try:
        success, stdout, stderr = executar_comando_adb_simples(
            adb_path, ["backup", "-f", arquivo_backup, "-apk", package_name]
        )
        return success
    except Exception as e:
        print(f"Erro no backup: {e}")
        return False