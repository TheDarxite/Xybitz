# xybitz-bootstrap: custom infrastructure setup script
# NOT a distutils/setuptools package definition
# DO NOT modify this file via Copilot scaffolding



#!/usr/bin/env python3
"""
Xybitz — L3 Launch-Ready Setup Script
Platform : Windows 10 / Ubuntu 20.04+ / Rocky Linux 8+
Usage    : python setup.py
Re-run   : safe to re-run at any time (idempotent)
"""

import getpass
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

# ─── Constants ────────────────────────────────────────────────────────────────
APP_NAME            = "Xybitz"
PYTHON_TARGET       = "3.12"
APP_PORT            = 8000
OLLAMA_PORT         = 11434
OLLAMA_MODEL_FAST   = "qwen2.5:1.5b"
OLLAMA_MODEL_QUAL   = "llama3.2:3b"

PROJECT_ROOT   = Path(__file__).parent.resolve()
VENV_DIR       = PROJECT_ROOT / ".venv"
DATA_DIR       = PROJECT_ROOT / "data"
ENV_FILE       = PROJECT_ROOT / ".env"
FEEDS_FILE     = DATA_DIR / "feeds.yaml"
REQ_FILE       = PROJECT_ROOT / "requirements.txt"

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX   = platform.system() == "Linux"
IS_MAC     = platform.system() == "Darwin"

# ─── Terminal Colors ──────────────────────────────────────────────────────────
class C:
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RESET  = "\033[0m"

def ok(msg):    print(f"{C.GREEN}  ✓  {msg}{C.RESET}")
def info(msg):  print(f"{C.CYAN}  ℹ  {msg}{C.RESET}")
def warn(msg):  print(f"{C.YELLOW}  ⚠  {msg}{C.RESET}")
def err(msg):   print(f"{C.RED}  ✗  {msg}{C.RESET}")
def step(n, msg): print(f"\n{C.BOLD}{C.CYAN}[Step {n}] {msg}{C.RESET}\n{'─'*52}")
def ask(prompt, default=""):
    try:
        val = input(f"{C.YELLOW}  → {prompt}{C.RESET}").strip()
        return val if val else default
    except (EOFError, KeyboardInterrupt):
        return default

# ─── Admin / Privilege Check ──────────────────────────────────────────────────
def check_privileges():
    if IS_WINDOWS:
        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
            if not is_admin:
                warn("Not running as Administrator.")
                warn("Python 3.12 auto-install via winget requires elevation.")
                warn("If Python 3.12 is already installed, this is fine.")
                choice = ask("Continue without admin? (y/n) [y]: ", "y")
                if choice.lower() == "n":
                    info("Right-click setup.py → 'Run as administrator', then re-run.")
                    sys.exit(0)
        except Exception:
            pass
    elif IS_LINUX:
        if os.geteuid() != 0:
            info("Running without root. System installs will use sudo.")

# ─── OS / Distro Detection ────────────────────────────────────────────────────
def detect_linux_distro() -> str:
    try:
        text = Path("/etc/os-release").read_text().lower()
        if "ubuntu" in text or "debian" in text or "mint" in text:
            return "debian"
        if "rocky" in text or "rhel" in text or "centos" in text or "fedora" in text:
            return "rhel"
    except Exception:
        pass
    return "debian"

# ─── Python 3.12 Detection & Install ─────────────────────────────────────────
def find_python312() -> str | None:
    """Search common Python 3.12 binary locations."""
    candidates = []
    if IS_WINDOWS:
        candidates = ["py", "python3.12", "python"]
        common_paths = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Python/Python312/python.exe",
            Path("C:/Python312/python.exe"),
            Path("C:/Program Files/Python312/python.exe"),
        ]
        for p in common_paths:
            if p.exists():
                return str(p)
    else:
        candidates = ["python3.12", "python3", "python"]

    for cmd in candidates:
        try:
            args = [cmd, "--version"] if cmd != "py" else ["py", "-3.12", "--version"]
            result = subprocess.run(args, capture_output=True, text=True, timeout=5)
            ver = result.stdout + result.stderr
            if "3.12" in ver:
                return shutil.which(cmd) or cmd
        except Exception:
            continue
    return None

def install_python312_windows() -> bool:
    info("Installing Python 3.12 via winget...")
    try:
        subprocess.run(
            [
                "winget", "install",
                "--id", "Python.Python.3.12",
                "--silent",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            check=True,
            timeout=300,
        )
        # Refresh PATH from registry
        try:
            new_path = subprocess.check_output(
                [
                    "powershell", "-NoProfile", "-Command",
                    "[Environment]::GetEnvironmentVariable('PATH','Machine') + ';' + "
                    "[Environment]::GetEnvironmentVariable('PATH','User')",
                ],
                text=True,
                timeout=10,
            ).strip()
            os.environ["PATH"] = new_path
        except Exception:
            pass
        ok("Python 3.12 installed via winget")
        return True
    except subprocess.CalledProcessError as e:
        err(f"winget install failed: {e}")
        info("Manual fallback: https://www.python.org/downloads/release/python-3129/")
        info("Download the Windows installer, install it, then re-run setup.py")
        return False

def install_python312_linux(distro: str) -> bool:
    info(f"Installing Python 3.12 on {distro}-based Linux...")
    try:
        if distro == "debian":
            subprocess.run(["sudo", "apt", "update", "-y"], check=True)
            # deadsnakes PPA for Ubuntu; on Debian pure, try direct
            try:
                subprocess.run(
                    ["sudo", "add-apt-repository", "-y", "ppa:deadsnakes/ppa"],
                    check=True, capture_output=True
                )
                subprocess.run(["sudo", "apt", "update", "-y"], check=True, capture_output=True)
            except Exception:
                pass
            subprocess.run(
                ["sudo", "apt", "install", "-y", "python3.12", "python3.12-venv", "python3.12-dev"],
                check=True
            )
        elif distro == "rhel":
            subprocess.run(
                ["sudo", "dnf", "install", "-y", "python3.12"],
                check=True
            )
        ok("Python 3.12 installed")
        return True
    except subprocess.CalledProcessError as e:
        err(f"Python 3.12 install failed: {e}")
        return False

def ensure_python312() -> str:
    step(1, "Python 3.12 Check")

    py = find_python312()
    if py:
        ok(f"Python 3.12 found → {py}")
        return py

    warn(f"Python 3.12 not found on this machine (you have {platform.python_version()}).")
    warn("Some libraries may have missing wheels on Python 3.14.")
    choice = ask("Auto-install Python 3.12? (y/n) [y]: ", "y")

    if choice.lower() == "n":
        warn("Continuing with system Python. Expect potential pip failures.")
        return sys.executable

    success = False
    if IS_WINDOWS:
        success = install_python312_windows()
    elif IS_LINUX:
        success = install_python312_linux(detect_linux_distro())
    elif IS_MAC:
        info("On macOS, run: brew install python@3.12")
        info("Then re-run setup.py")
        sys.exit(1)

    if not success:
        warn("Falling back to current Python. Proceed with caution.")
        return sys.executable

    py = find_python312()
    if not py:
        warn("Python 3.12 installed but not in PATH yet.")
        warn("Please open a new terminal and re-run setup.py")
        sys.exit(1)

    ok(f"Python 3.12 ready → {py}")
    return py

# ─── Virtual Environment ──────────────────────────────────────────────────────
def get_venv_bin(name: str) -> str:
    if IS_WINDOWS:
        return str(VENV_DIR / "Scripts" / f"{name}.exe")
    return str(VENV_DIR / "bin" / name)

def ensure_venv(python312: str) -> str:
    step(2, "Virtual Environment")
    venv_python = get_venv_bin("python")

    if VENV_DIR.exists() and Path(venv_python).exists():
        ok(f"venv exists → {VENV_DIR}")
        return venv_python

    if VENV_DIR.exists():
        warn("Stale venv detected — recreating...")
        shutil.rmtree(VENV_DIR)

    info(f"Creating venv with Python 3.12 at {VENV_DIR} ...")
    subprocess.run([python312, "-m", "venv", str(VENV_DIR)], check=True)
    ok("Virtual environment created")
    return venv_python

# ─── Requirements ─────────────────────────────────────────────────────────────
REQUIREMENTS = """\
fastapi==0.115.0
uvicorn[standard]==0.30.0
jinja2==3.1.4
sqlalchemy[asyncio]==2.0.35
aiosqlite==0.20.0
feedparser==6.0.11
trafilatura==1.12.0
httpx==0.27.0
apscheduler==3.10.4
pydantic-settings==2.4.0
python-dotenv==1.0.1
pyyaml==6.0.2
sqladmin==0.19.0
itsdangerous==2.2.0
playwright==1.47.0
"""

REQUIREMENTS_DEV = """\
pytest==8.3.0
pytest-asyncio==0.23.0
pytest-cov==5.0.0
ruff==0.6.0
httpx==0.27.0
"""

def ensure_requirements(venv_python: str):
    step(3, "Python Dependencies")

    if not REQ_FILE.exists():
        info("requirements.txt not found — generating from embedded defaults...")
        REQ_FILE.write_text(REQUIREMENTS)
        (PROJECT_ROOT / "requirements-dev.txt").write_text(REQUIREMENTS_DEV)
        ok("requirements.txt + requirements-dev.txt created")

    info("Upgrading pip...")
    subprocess.run(
        [venv_python, "-m", "pip", "install", "--upgrade", "pip"],
        capture_output=True, check=True
    )

    info("Installing dependencies (first run: ~2-4 minutes)...")
    result = subprocess.run(
        [venv_python, "-m", "pip", "install", "-r", str(REQ_FILE)],
        text=True, capture_output=True
    )

    if result.returncode != 0:
        err("pip install failed. Last 3000 chars of error:")
        print(result.stderr[-3000:])

        # Retry without version pins (fallback for Python 3.14)
        warn("Retrying without strict version pins...")
        relaxed = "\n".join(
            line.split("==")[0]
            for line in REQUIREMENTS.strip().split("\n")
            if line and not line.startswith("#")
        )
        tmp = Path(tempfile.mktemp(suffix=".txt"))
        tmp.write_text(relaxed)
        result2 = subprocess.run(
            [venv_python, "-m", "pip", "install", "-r", str(tmp)],
            text=True, capture_output=True
        )
        tmp.unlink(missing_ok=True)
        if result2.returncode != 0:
            err("Retry also failed. See output:")
            print(result2.stderr[-2000:])
            sys.exit(1)
        warn("Installed with relaxed versions — check for compat issues manually.")

    ok("All Python dependencies installed")

    # Playwright Chromium
    info("Installing Playwright Chromium (needed for JS-rendered scrape targets)...")
    pw_result = subprocess.run(
        [venv_python, "-m", "playwright", "install", "chromium"],
        capture_output=True, text=True
    )
    if pw_result.returncode == 0:
        ok("Playwright Chromium ready")
    else:
        warn("Playwright Chromium install failed — Tier 3 scraping will be unavailable")

# ─── LLM Backend Configuration ───────────────────────────────────────────────
def configure_llm_backend() -> dict:
    step(4, "LLM Backend Configuration")

    print(f"""
  {C.BOLD}Choose your LLM backend:{C.RESET}

  {C.BOLD}1. Local Ollama{C.RESET} — free, private, runs on this machine   {C.GREEN}[recommended]{C.RESET}
  {C.BOLD}2. Remote Ollama{C.RESET} — Ollama on another machine (e.g., home server with GPU)
  {C.BOLD}3. OpenAI API{C.RESET} — paid, cloud, highest quality
  {C.BOLD}4. Groq API{C.RESET} — free tier, cloud, very fast (llama-3.1 hosted)
""")
    choice = ask("Select [1-4, default=1]: ", "1")

    if choice == "2":
        host = ask(f"Remote Ollama host:port [e.g., 192.168.1.10:{OLLAMA_PORT}]: ",
                   f"192.168.1.10:{OLLAMA_PORT}")
        model = ask(f"Model name [default={OLLAMA_MODEL_FAST}]: ", OLLAMA_MODEL_FAST)
        return {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_BASE_URL": f"http://{host}",
            "OLLAMA_MODEL": model,
        }

    elif choice == "3":
        api_key = getpass.getpass("  → OpenAI API Key: ")
        return {
            "LLM_PROVIDER": "openai",
            "OPENAI_API_KEY": api_key,
            "OPENAI_MODEL": "gpt-4o-mini",
            "OLLAMA_BASE_URL": "",
            "OLLAMA_MODEL": "",
        }

    elif choice == "4":
        info("Get a free key at: https://console.groq.com")
        api_key = getpass.getpass("  → Groq API Key: ")
        return {
            "LLM_PROVIDER": "groq",
            "GROQ_API_KEY": api_key,
            "GROQ_MODEL": "llama-3.1-8b-instant",
            "OLLAMA_BASE_URL": "",
            "OLLAMA_MODEL": "",
        }

    else:
        # Default: local Ollama
        print(f"""
  {C.BOLD}Model selection:{C.RESET}
  a. {OLLAMA_MODEL_FAST} — faster (~8s/article), 1 GB RAM  {C.GREEN}[best for your i5]{C.RESET}
  b. {OLLAMA_MODEL_QUAL} — better quality (~18s/article), 2 GB RAM
""")
        m = ask("Select [a/b, default=a]: ", "a")
        model = OLLAMA_MODEL_QUAL if m.lower() == "b" else OLLAMA_MODEL_FAST
        return {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_BASE_URL": f"http://localhost:{OLLAMA_PORT}",
            "OLLAMA_MODEL": model,
        }

# ─── Ollama Install + Start ───────────────────────────────────────────────────
def is_ollama_running() -> bool:
    try:
        with urllib.request.urlopen(
            f"http://localhost:{OLLAMA_PORT}/api/tags", timeout=3
        ) as r:
            return r.status == 200
    except Exception:
        return False

def is_model_available(model: str) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://localhost:{OLLAMA_PORT}/api/tags", timeout=5
        ) as r:
            data = json.loads(r.read())
            names = [m.get("name", "") for m in data.get("models", [])]
            return any(model.split(":")[0] in n for n in names)
    except Exception:
        return False

def install_ollama_windows() -> bool:
    info("Downloading Ollama Windows installer...")
    url = "https://ollama.com/download/OllamaSetup.exe"
    dest = Path(tempfile.gettempdir()) / "OllamaSetup.exe"
    try:
        def progress(count, block, total):
            pct = min(int(count * block * 100 / total), 100)
            print(f"  Downloading: {pct}%", end="\r")
        urllib.request.urlretrieve(url, dest, reporthook=progress)
        print()
        info("Running Ollama installer silently (takes ~30s)...")
        subprocess.run([str(dest), "/S"], check=True, timeout=120)
        # Refresh PATH
        try:
            machine_path = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command",
                 "[Environment]::GetEnvironmentVariable('PATH','Machine')"],
                text=True, timeout=10
            ).strip()
            os.environ["PATH"] = machine_path + ";" + os.environ.get("PATH", "")
        except Exception:
            pass
        ok("Ollama installed on Windows")
        return True
    except Exception as e:
        err(f"Ollama Windows install failed: {e}")
        info("Manual install: https://ollama.com/download")
        return False

def install_ollama_linux() -> bool:
    info("Installing Ollama via official Linux script...")
    try:
        subprocess.run(
            "curl -fsSL https://ollama.com/install.sh | sh",
            shell=True, check=True
        )
        ok("Ollama installed on Linux")
        return True
    except subprocess.CalledProcessError as e:
        err(f"Ollama Linux install failed: {e}")
        return False

def start_ollama_service():
    if is_ollama_running():
        ok("Ollama already running")
        return

    info("Starting Ollama in background...")
    try:
        if IS_WINDOWS:
            subprocess.Popen(
                ["ollama", "serve"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except FileNotFoundError:
        warn("'ollama' not found in PATH after install — may need terminal restart")
        return

    for i in range(30):
        time.sleep(1)
        if is_ollama_running():
            ok("Ollama is running and accepting requests")
            return
        print(f"  Waiting for Ollama to start... ({i+1}s)", end="\r")
    print()
    warn("Ollama did not start within 30s — model pull may fail")

def pull_model(model: str):
    if is_model_available(model):
        ok(f"Model '{model}' already pulled")
        return
    info(f"Pulling model '{model}' — first pull may take 5-15 min depending on connection...")
    try:
        subprocess.run(["ollama", "pull", model], check=True, timeout=900)
        ok(f"Model '{model}' ready")
    except subprocess.CalledProcessError:
        warn(f"Model pull failed — articles will queue as 'pending' until model is available")
    except subprocess.TimeoutExpired:
        warn("Model pull timed out — run 'ollama pull {model}' manually")

def setup_ollama(llm_config: dict):
    step(5, "Ollama Setup")

    if llm_config["LLM_PROVIDER"] != "ollama":
        ok(f"Cloud LLM selected ({llm_config['LLM_PROVIDER']}) — skipping Ollama")
        return

    if "localhost" not in llm_config.get("OLLAMA_BASE_URL", ""):
        ok(f"Remote Ollama configured — skipping local install")
        return

    if shutil.which("ollama"):
        ok("Ollama already installed")
    else:
        warn("Ollama not found — installing...")
        success = install_ollama_windows() if IS_WINDOWS else install_ollama_linux()
        if not success:
            warn("Skipping Ollama — install manually from https://ollama.com")
            return

    start_ollama_service()

    if is_ollama_running():
        pull_model(llm_config.get("OLLAMA_MODEL", OLLAMA_MODEL_FAST))
    else:
        warn("Ollama not reachable — skipping model pull. Run 'ollama serve' manually.")

# ─── .env Generation ──────────────────────────────────────────────────────────
def generate_env(llm_config: dict):
    step(6, ".env Configuration")

    if ENV_FILE.exists():
        ow = ask(".env already exists. Overwrite? (y/n) [n]: ", "n")
        if ow.lower() != "y":
            ok("Keeping existing .env")
            return

    print(f"  {C.DIM}Leave blank to accept defaults{C.RESET}")
    admin_user = ask("Admin username [default=admin]: ", "admin")
    admin_pass = getpass.getpass("  → Admin password [default=xybitz@admin]: ") or "xybitz@admin"

    lines = {
        "APP_NAME":                    "Xybitz",
        "DEBUG":                       "true",
        "DATABASE_URL":                "sqlite+aiosqlite:///./data/xybitz.db",
        "LLM_PROVIDER":                llm_config.get("LLM_PROVIDER", "ollama"),
        "OLLAMA_BASE_URL":             llm_config.get("OLLAMA_BASE_URL", ""),
        "OLLAMA_MODEL":                llm_config.get("OLLAMA_MODEL", ""),
        "OPENAI_API_KEY":              llm_config.get("OPENAI_API_KEY", ""),
        "OPENAI_MODEL":                llm_config.get("OPENAI_MODEL", ""),
        "GROQ_API_KEY":                llm_config.get("GROQ_API_KEY", ""),
        "GROQ_MODEL":                  llm_config.get("GROQ_MODEL", ""),
        "SUMMARY_WORD_TARGET":         "55",
        "FETCH_INTERVAL_MINUTES":      "30",
        "ARTICLE_RETENTION_DAYS":      "3",
        "INITIAL_BACKFILL_DAYS":       "3",
        "SUMMARISATION_CONCURRENCY":   "3",
        "FEEDS_CONFIG_PATH":           "./data/feeds.yaml",
        "ADMIN_USERNAME":              admin_user,
        "ADMIN_PASSWORD":              admin_pass,
    }

    content = "\n".join(f"{k}={v}" for k, v in lines.items()) + "\n"
    ENV_FILE.write_text(content)

    # .env.example — same but with secrets blanked
    example = "\n".join(
        f"{k}=<your-{k.lower().replace('_', '-')}>"
        if "key" in k.lower() or "password" in k.lower()
        else f"{k}={v}"
        for k, v in lines.items()
    ) + "\n"
    (PROJECT_ROOT / ".env.example").write_text(example)
    ok(".env written")
    ok(".env.example written (safe to commit)")

# ─── feeds.yaml ───────────────────────────────────────────────────────────────
FEEDS_YAML = """\
feeds:
  # ── THREAT INTEL ────────────────────────────────────────────
  - {name: "The Hacker News",    url: "https://feeds.feedburner.com/TheHackersNews",   category: threat_intel, type: rss}
  - {name: "Dark Reading",       url: "https://www.darkreading.com/rss.xml",            category: threat_intel, type: rss}
  - {name: "Krebs on Security",  url: "https://krebsonsecurity.com/feed/",              category: threat_intel, type: rss}
  - {name: "CyberScoop",         url: "https://cyberscoop.com/feed/",                  category: threat_intel, type: rss}
  - {name: "The Cyber Express",  url: "https://thecyberexpress.com/feed/",              category: threat_intel, type: rss}
  - {name: "GBHackers",          url: "https://gbhackers.com/feed/",                   category: threat_intel, type: rss}
  - {name: "Cybernews",          url: "https://cybernews.com/feed/",                   category: threat_intel, type: rss}

  # ── VULNERABILITIES ─────────────────────────────────────────
  - {name: "CISA Alerts",        url: "https://www.cisa.gov/cybersecurity-advisories/all.xml", category: vulnerabilities, type: rss}
  - {name: "NVD CVE Feed",       url: "https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss.xml",   category: vulnerabilities, type: rss}
  - {name: "SecurityWeek",       url: "https://feeds.feedburner.com/Securityweek",              category: vulnerabilities, type: rss}

  # ── MALWARE ──────────────────────────────────────────────────
  - {name: "Bleeping Computer",       url: "https://www.bleepingcomputer.com/feed/",           category: malware, type: rss}
  - {name: "We Live Security (ESET)", url: "https://www.welivesecurity.com/en/rss/feed/",      category: malware, type: rss}
  - {name: "Sophos News",             url: "https://news.sophos.com/en-us/feed/",              category: malware, type: rss}
  - {name: "Cyble Blog",              url: "https://cyble.com/feed/",                          category: malware, type: rss}

  # ── APP SECURITY ─────────────────────────────────────────────
  - {name: "Google Project Zero", url: "https://googleprojectzero.blogspot.com/feeds/posts/default", category: appsec, type: rss}
  - {name: "PortSwigger",         url: "https://portswigger.net/blog/rss",                           category: appsec, type: rss}

  # ── CLOUD SECURITY ───────────────────────────────────────────
  - {name: "Wiz Security Blog",    url: "https://www.wiz.io/feed/rss.xml",                    category: cloud_security, type: rss}
  - {name: "AWS Security Blog",    url: "https://aws.amazon.com/blogs/security/feed/",         category: cloud_security, type: rss}
  - {name: "Palo Alto Networks",   url: "https://feeds.feedburner.com/PaloAltoNetworksBlog",   category: cloud_security, type: rss}

  # ── COMPLIANCE ───────────────────────────────────────────────
  - {name: "Schneier on Security", url: "https://www.schneier.com/feed/atom/",                    category: compliance, type: rss}
  - {name: "NIST Cybersecurity",   url: "https://www.nist.gov/blogs/cybersecurity-insights/rss.xml", category: compliance, type: rss}

  # ── PRIVACY ──────────────────────────────────────────────────
  - {name: "Graham Cluley",              url: "https://grahamcluley.com/feed/",                                       category: privacy, type: rss}
  - {name: "Troy Hunt",                  url: "https://www.troyhunt.com/rss/",                                        category: privacy, type: rss}
  - {name: "The Guardian Data Security", url: "https://www.theguardian.com/technology/data-computer-security/rss",    category: privacy, type: rss}

  # ── AI SECURITY ──────────────────────────────────────────────
  - {name: "Reco AI Blog",          url: "https://www.reco.ai/blog/rss.xml",                        category: ai_security, type: rss}
  - {name: "Google Online Security", url: "https://feeds.feedburner.com/GoogleOnlineSecurityBlog",   category: ai_security, type: rss}
  - {name: "MIT Cybersecurity",      url: "https://news.mit.edu/topic/mitcybersecurity.rss",          category: ai_security, type: rss}

  # ── SCRAPE TIER (no RSS) ─────────────────────────────────────
  - name: "Cyware News"
    url: "https://social.cyware.com/cyber-security-news-articles"
    category: threat_intel
    type: scrape_static
    scrape_engine: httpx
    list_selector: "div.card-body"
    link_selector: "a.news-title"
    rate_limit_seconds: 60
"""

def ensure_data_files():
    step(7, "Data Directory + feeds.yaml")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not FEEDS_FILE.exists():
        FEEDS_FILE.write_text(FEEDS_YAML)
        ok(f"feeds.yaml created with 28 sources → {FEEDS_FILE}")
    else:
        ok("feeds.yaml already exists — keeping as-is")

# ─── .gitignore ───────────────────────────────────────────────────────────────
GITIGNORE = """\
.venv/
__pycache__/
*.pyc
*.pyo
.env
data/xybitz.db
data/xybitz.db-wal
data/xybitz.db-shm
.pytest_cache/
htmlcov/
.coverage
dist/
build/
*.egg-info/
.DS_Store
Thumbs.db
"""

def ensure_gitignore():
    gi = PROJECT_ROOT / ".gitignore"
    if not gi.exists():
        gi.write_text(GITIGNORE)
        ok(".gitignore created")
    else:
        ok(".gitignore already exists")

# ─── Makefile ─────────────────────────────────────────────────────────────────
MAKEFILE = """\
VENV_PYTHON := .venv/bin/python
ifeq ($(OS),Windows_NT)
    VENV_PYTHON := .venv/Scripts/python.exe
endif

dev:
\tuvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
\t$(VENV_PYTHON) -m pytest tests/ -v --asyncio-mode=auto

test-cov:
\t$(VENV_PYTHON) -m pytest tests/ --cov=app --cov-report=html

lint:
\t$(VENV_PYTHON) -m ruff check app/ tests/

format:
\t$(VENV_PYTHON) -m ruff format app/ tests/

db-reset:
\trm -f data/xybitz.db data/xybitz.db-wal data/xybitz.db-shm

setup:
\tpython setup.py

install:
\t$(VENV_PYTHON) -m pip install -r requirements.txt

.PHONY: dev test test-cov lint format db-reset setup install
"""

def ensure_makefile():
    mf = PROJECT_ROOT / "Makefile"
    if not mf.exists():
        mf.write_text(MAKEFILE)
        ok("Makefile created")

# ─── Database Init ────────────────────────────────────────────────────────────
def initialize_database(venv_python: str):
    step(8, "Database Initialization")

    main_py = PROJECT_ROOT / "app" / "main.py"
    if not main_py.exists():
        warn("app/main.py not found — DB init will run after Copilot generates app code")
        return

    init_script = """\
import asyncio, sys
sys.path.insert(0, '.')
async def run():
    from app.database import create_all_tables
    await create_all_tables()
    print("  DB tables created successfully")
asyncio.run(run())
"""
    tmp = PROJECT_ROOT / "_xybitz_db_init_tmp.py"
    tmp.write_text(init_script)

    result = subprocess.run(
        [venv_python, str(tmp)],
        cwd=str(PROJECT_ROOT),
        capture_output=True, text=True
    )
    tmp.unlink(missing_ok=True)

    if result.returncode == 0:
        ok("Database initialized")
        print(f"  {C.DIM}{result.stdout.strip()}{C.RESET}")
    else:
        warn("DB init skipped — re-runs automatically when app starts")

# ─── Project Mode Detection ───────────────────────────────────────────────────
def detect_mode() -> str:
    """
    repo    → app/main.py exists (cloned from git, code is there)
    partial → app/ exists but main.py missing
    fresh   → no app/ directory at all
    """
    app_dir = PROJECT_ROOT / "app"
    if (app_dir / "main.py").exists():
        return "repo"
    if app_dir.exists():
        return "partial"
    return "fresh"

# ─── Launch ───────────────────────────────────────────────────────────────────
def launch_app(venv_python: str):
    step(9, "Launching Xybitz 🚀")

    uvicorn = get_venv_bin("uvicorn")
    if not Path(uvicorn).exists():
        err("uvicorn not found in venv — run pip install again")
        return

    url = f"http://localhost:{APP_PORT}"
    admin_url = f"{url}/admin"

    print(f"""
  {C.BOLD}Xybitz is starting...{C.RESET}
  Web app   → {C.CYAN}{url}{C.RESET}
  Admin     → {C.CYAN}{admin_url}{C.RESET}
  Health    → {C.CYAN}{url}/health{C.RESET}

  {C.DIM}Press Ctrl+C to stop{C.RESET}
""")

    def _open_browser():
        time.sleep(3)
        webbrowser.open(url)

    threading.Thread(target=_open_browser, daemon=True).start()

    try:
        subprocess.run(
            [uvicorn, "app.main:app",
             "--reload", "--host", "0.0.0.0", "--port", str(APP_PORT)],
            cwd=str(PROJECT_ROOT)
        )
    except KeyboardInterrupt:
        print(f"\n  {C.YELLOW}Xybitz stopped.{C.RESET}")

# ─── Summary Banner ───────────────────────────────────────────────────────────
def print_next_steps(mode: str, llm_config: dict):
    model = llm_config.get("OLLAMA_MODEL") or llm_config.get("GROQ_MODEL") or llm_config.get("OPENAI_MODEL", "")

    print(f"""
{C.GREEN}{C.BOLD}  ╔══════════════════════════════════════════════════╗
  ║         ✅  Xybitz Setup Complete                ║
  ╚══════════════════════════════════════════════════╝{C.RESET}

  {C.BOLD}What was set up:{C.RESET}
  ✓  Python 3.12 virtual environment → .venv/
  ✓  All pip dependencies installed
  ✓  Ollama ready, model: {model}
  ✓  .env configured
  ✓  data/feeds.yaml (28 sources, 8 categories)
  ✓  Makefile, .gitignore, requirements.txt
""")

    if mode == "fresh":
        print(f"""\
  {C.BOLD}{C.YELLOW}Next: Generate app code with Copilot{C.RESET}

  1. Open VS Code:
     {C.CYAN}code .{C.RESET}

  2. Open Copilot Chat → Agent mode
     {C.DIM}Ctrl+Shift+I → select "Agent"{C.RESET}

  3. Paste the Xybitz master prompt (from your build notes)

  4. Once code is generated, re-run this script:
     {C.CYAN}python setup.py{C.RESET}
     → It will detect the code, init DB, and launch the app
""")
    else:
        print(f"""\
  {C.BOLD}To start Xybitz anytime:{C.RESET}
  {C.CYAN}python setup.py{C.RESET}         → full setup + launch
  {C.CYAN}make dev{C.RESET}               → just launch (code already set up)
  {C.CYAN}make test{C.RESET}              → run test suite
  {C.CYAN}make db-reset{C.RESET}          → wipe DB and start fresh
""")

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    if IS_WINDOWS:
        os.system("color")  # Enable ANSI on Windows 10 terminal

    print(f"""{C.BOLD}{C.CYAN}
  ██╗  ██╗██╗   ██╗██████╗ ██╗████████╗███████╗
  ╚██╗██╔╝╚██╗ ██╔╝██╔══██╗██║╚══██╔══╝╚══███╔╝
   ╚███╔╝  ╚████╔╝ ██████╔╝██║   ██║     ███╔╝
   ██╔██╗   ╚██╔╝  ██╔══██╗██║   ██║    ███╔╝
  ██╔╝ ██╗   ██║   ██████╔╝██║   ██║   ███████╗
  ╚═╝  ╚═╝   ╚═╝   ╚═════╝ ╚═╝   ╚═╝   ╚══════╝
{C.RESET}
  {C.BOLD}CyberSec News · AI-Summarised · Always Current{C.RESET}
  {C.DIM}Setup v1.0 · {platform.system()} {platform.release()} · Python {platform.python_version()}{C.RESET}
""")

    check_privileges()

    # Detect project mode
    mode = detect_mode()
    step(0, "Project Mode Detection")
    mode_labels = {
        "repo":    "Repo mode   — app code found, running infra setup",
        "partial": "Partial     — some files missing, setting up infra",
        "fresh":   "Fresh start — no code yet, setting up infra only",
    }
    info(mode_labels[mode])

    # Run all setup steps
    python312  = ensure_python312()
    venv_py    = ensure_venv(python312)
    ensure_requirements(venv_py)
    llm_config = configure_llm_backend()
    setup_ollama(llm_config)
    generate_env(llm_config)
    ensure_data_files()
    ensure_gitignore()
    ensure_makefile()
    initialize_database(venv_py)

    print_next_steps(mode, llm_config)

    # Launch if code exists
    if mode == "repo" and (PROJECT_ROOT / "app" / "main.py").exists():
        launch = ask("Launch Xybitz now? (y/n) [y]: ", "y")
        if launch.lower() != "n":
            launch_app(venv_py)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  {C.YELLOW}Setup interrupted. Re-run anytime with: python setup.py{C.RESET}\n")
        sys.exit(0)
