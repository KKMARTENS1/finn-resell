"""Oppdatering av Golflager fra GitHub med ett klikk.

Slik gjøres en oppdatering, så en feil aldri ødelegger appen du har:
1. Den nye versjonen lastes ned og pakkes ut i en egen mappe.
2. Den prøvekjøres mot en kopi av dataene dine. Feiler det, endres ingenting.
3. Den gamle versjonen tas vare på i ~/Golflager/forrige-versjon.
4. De nye filene kopieres inn, og Golflager startes på nytt.
"""
from __future__ import annotations

import io
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import requests

from .config import APP_DIR
from .db import get_settings, now_str, set_setting

log = logging.getLogger(__name__)

REPO = os.environ.get("GOLFLAGER_REPO", "KKMARTENS1/finn-resell")
PROJECT_DIR = APP_DIR.parent
VERSION_FILE = "VERSJON"
CHECK_EVERY = timedelta(hours=12)
TIMEOUT = 30
REQUIRED = ("start.sh", "run.py", "requirements.txt", "golflager/__init__.py", VERSION_FILE)
SKIP = {".venv", ".git", "__pycache__", ".pytest_cache", "node_modules"}
HEADERS = {"User-Agent": "Golflager-oppdatering", "Accept": "application/vnd.github+json"}

# Prøvekjøring av den nye versjonen mot en kopi av databasen
PREFLIGHT = """
import sys
sys.path.insert(0, sys.argv[1])
from golflager import create_app
app = create_app(sys.argv[2], start_scraper=False)
client = app.test_client()
for path in ("/", "/funn", "/lager", "/prissjekk", "/markedspriser", "/sok", "/innstillinger"):
    status = client.get(path).status_code
    if status != 200:
        raise SystemExit(f"{path} svarte {status}")
print("ok")
"""


class UpdateError(Exception):
    """Oppdateringen kunne ikke gjøres. Ingenting er endret."""


def parse_version(text: Optional[str]) -> Tuple[int, ...]:
    parts = re.findall(r"\d+", text or "")
    return tuple(int(p) for p in parts) if parts else (0,)


def local_version(project_dir: Path = PROJECT_DIR) -> str:
    try:
        return (project_dir / VERSION_FILE).read_text(encoding="utf-8").strip() or "0"
    except OSError:
        return "0"


def is_newer(remote: Optional[str], local: Optional[str]) -> bool:
    return bool(remote) and parse_version(remote) > parse_version(local)


# ---------------------------------------------------------------------------
# GitHub


def _get(url: str, **headers: str) -> requests.Response:
    try:
        response = requests.get(url, headers={**HEADERS, **headers}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise UpdateError("Fikk ikke kontakt med GitHub. Sjekk internettforbindelsen.") from exc
    if response.status_code == 404:
        raise UpdateError(
            "Fant ikke Golflager på GitHub. Prosjektet må være offentlig for at "
            "oppdateringsknappen skal virke."
        )
    if response.status_code != 200:
        raise UpdateError(f"GitHub svarte med feilkode {response.status_code}. Prøv igjen senere.")
    return response


def default_branch() -> str:
    return _get(f"https://api.github.com/repos/{REPO}").json().get("default_branch") or "main"


def remote_version(branch: str) -> str:
    response = _get(f"https://api.github.com/repos/{REPO}/contents/{VERSION_FILE}?ref={branch}",
                    Accept="application/vnd.github.raw")
    return response.text.strip()


def fetch_zip(branch: str) -> bytes:
    return _get(f"https://codeload.github.com/{REPO}/zip/refs/heads/{branch}").content


# ---------------------------------------------------------------------------
# Se etter ny versjon


def check_for_update(conn: sqlite3.Connection, force: bool = False) -> Optional[str]:
    """Ser etter ny versjon (maks hver 12. time). Returnerer den nye versjonen, eller None."""
    settings = get_settings(conn)
    try:
        last = datetime.fromisoformat(settings["update_checked_at"])
    except ValueError:
        last = None
    if not force and last is not None and datetime.now() - last < CHECK_EVERY:
        stored = settings["update_available"]
        return stored if is_newer(stored, local_version()) else None
    try:
        remote = remote_version(default_branch())
    except UpdateError:
        # Prøv igjen om en time i stedet for å mase på GitHub
        retry_from = datetime.now() - CHECK_EVERY + timedelta(hours=1)
        set_setting(conn, "update_checked_at", retry_from.replace(microsecond=0).isoformat(sep=" "))
        conn.commit()
        raise
    set_setting(conn, "update_available", remote if is_newer(remote, local_version()) else "")
    set_setting(conn, "update_checked_at", now_str())
    conn.commit()
    return remote if is_newer(remote, local_version()) else None


# ---------------------------------------------------------------------------
# Installer


def _extract(data: bytes, staging: Path) -> str:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UpdateError("Nedlastingen var ødelagt. Prøv igjen.") from exc
    with archive:
        names = archive.namelist()
        top = names[0].split("/")[0] + "/" if names else ""
        for required in REQUIRED:
            if top + required not in names:
                raise UpdateError("Nedlastingen ser ikke ut som Golflager. Ingenting er endret.")
        for info in archive.infolist():
            relative = info.filename[len(top):]
            if not relative or info.is_dir():
                continue
            parts = Path(relative).parts
            if relative.startswith("/") or ".." in parts:
                raise UpdateError("Nedlastingen inneholdt ugyldige filnavn. Ingenting er endret.")
            if parts[0] in SKIP or "__pycache__" in parts:
                continue
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
            if (info.external_attr >> 16) & 0o111:
                target.chmod(0o755)
    for script in ("start.sh", "Start.command", "mac/Golflager", "mac/lag-app.sh"):
        if (staging / script).exists():
            (staging / script).chmod(0o755)
    return (staging / VERSION_FILE).read_text(encoding="utf-8").strip()


def _run(args: list, cwd: Path, what: str, log_file: Path) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GOLFLAGER_")}
    result = subprocess.run(args, cwd=str(cwd), env=env, capture_output=True, text=True,
                            timeout=600)
    if result.returncode != 0:
        details = (result.stdout + "\n" + result.stderr).strip()
        try:
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(f"\n=== {now_str()} oppdatering: {what} feilet\n{details}\n")
        except OSError:
            pass
        raise UpdateError(
            f"Den nye versjonen besto ikke prøven ({what}), så ingenting er endret. "
            f"Detaljer ligger i {log_file}."
        )


def install_latest(database: str, project_dir: Path = PROJECT_DIR,
                   python: str = sys.executable) -> str:
    """Laster ned, prøvekjører og installerer nyeste versjon. Returnerer versjonsnummeret."""
    data_dir = Path(database).parent
    log_file = data_dir / "feilsøking" / "feillogg.txt"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    branch = default_branch()
    work = Path(tempfile.mkdtemp(prefix="golflager-oppdatering-"))
    try:
        staging = work / "ny"
        staging.mkdir()
        new_version = _extract(fetch_zip(branch), staging)

        # Nye pakker installeres først. Det skader ikke versjonen som kjører nå.
        old_requirements = (project_dir / "requirements.txt").read_bytes() \
            if (project_dir / "requirements.txt").exists() else b""
        if (staging / "requirements.txt").read_bytes() != old_requirements:
            _run([python, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r",
                  str(staging / "requirements.txt")], staging, "installere pakker", log_file)

        # Prøvekjør mot en kopi av dataene dine
        copy = work / "prøve.db"
        with sqlite3.connect(database) as source, sqlite3.connect(str(copy)) as target:
            source.backup(target)
        _run([python, "-c", PREFLIGHT, str(staging), str(copy)], staging, "prøvekjøring",
             log_file)

        # Ta vare på den gamle versjonen, og kopier inn den nye
        backup = data_dir / "forrige-versjon"
        shutil.rmtree(backup, ignore_errors=True)
        shutil.copytree(project_dir, backup, ignore=shutil.ignore_patterns(*SKIP, "*.pyc"))
        for source_file in staging.rglob("*"):
            if source_file.is_file():
                target_file = project_dir / source_file.relative_to(staging)
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, target_file)

        # Oppdater Golflager-ikonet i Dock
        if sys.platform == "darwin" and (project_dir / "mac" / "lag-app.sh").exists():
            subprocess.run(["bash", str(project_dir / "mac" / "lag-app.sh"), str(project_dir)],
                           capture_output=True, timeout=60)
        return new_version
    finally:
        shutil.rmtree(work, ignore_errors=True)


def restart(project_dir: Path = PROJECT_DIR, log_path: Optional[Path] = None) -> None:
    """Starter Golflager på nytt i bakgrunnen litt etter at denne versjonen har stoppet."""
    env = dict(os.environ, GOLFLAGER_FRA_APP="1", GOLFLAGER_NO_BROWSER="1")
    output = open(log_path, "a", encoding="utf-8") if log_path else subprocess.DEVNULL
    subprocess.Popen(
        ["/bin/bash", "-c", "sleep 2; exec bash start.sh"],
        cwd=str(project_dir), env=env, stdin=subprocess.DEVNULL, stdout=output,
        stderr=subprocess.STDOUT, start_new_session=True,
    )
