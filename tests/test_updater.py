import io
import os
import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from golflager import updater
from golflager.db import get_settings, set_setting

ROOT = Path(__file__).resolve().parent.parent
TOP = "finn-resell-main/"


def make_zip(version="9.9", mutate=None, extra=None):
    """Lager en ZIP slik GitHub gjør det, av filene i dette prosjektet."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in sorted(ROOT.rglob("*")):
            relative = path.relative_to(ROOT)
            if (path.is_dir() or relative.parts[0] in updater.SKIP | {"tests"}
                    or "__pycache__" in relative.parts):
                continue
            data = path.read_bytes()
            if relative.as_posix() == "VERSJON":
                data = version.encode()
            if mutate:
                data = mutate(relative.as_posix(), data)
            info = zipfile.ZipInfo(TOP + relative.as_posix())
            mode = 0o755 if os.access(path, os.X_OK) else 0o644
            info.external_attr = (0o100000 | mode) << 16
            archive.writestr(info, data)
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


@pytest.fixture
def project(tmp_path):
    """En «gammel» installasjon, uten versjonsfil, slik brukeren har i dag."""
    target = tmp_path / "app"
    shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns(
        ".git", ".venv", "__pycache__", ".pytest_cache", "tests"))
    version = target / "VERSJON"
    if version.exists():
        version.unlink()
    (target / "start.sh").chmod(0o644)
    return target


@pytest.fixture
def github(monkeypatch):
    calls = []
    monkeypatch.setattr(updater, "default_branch", lambda: calls.append("branch") or "main")
    return calls


def test_versions_are_compared_as_numbers():
    assert updater.is_newer("1.10", "1.9")
    assert updater.is_newer("1.3", "0")
    assert not updater.is_newer("1.3", "1.3")
    assert not updater.is_newer("", "1.3")


def test_update_replaces_code_keeps_backup(project, db_path, github, monkeypatch):
    marker = b"\n<!-- ny versjon -->\n"
    monkeypatch.setattr(updater, "fetch_zip", lambda branch: make_zip(
        "9.9", mutate=lambda name, data: data + marker if name == "README.md" else data))
    assert updater.install_latest(db_path, project_dir=project) == "9.9"
    assert (project / "VERSJON").read_text() == "9.9"
    assert (project / "README.md").read_bytes().endswith(marker)
    assert os.access(project / "start.sh", os.X_OK)
    backup = Path(db_path).parent / "forrige-versjon"
    assert (backup / "run.py").exists() and not (backup / "VERSJON").exists()


def test_broken_new_version_changes_nothing(project, db_path, github, monkeypatch):
    before = (project / "golflager" / "views.py").read_bytes()
    monkeypatch.setattr(updater, "fetch_zip", lambda branch: make_zip(
        mutate=lambda name, data: data + b"\nthis is not python(\n"
        if name == "golflager/views.py" else data))
    with pytest.raises(updater.UpdateError) as err:
        updater.install_latest(db_path, project_dir=project)
    assert "ingenting er endret" in str(err.value)
    assert (project / "golflager" / "views.py").read_bytes() == before
    assert not (project / "VERSJON").exists()
    assert not (Path(db_path).parent / "forrige-versjon").exists()
    assert "prøvekjøring" in (Path(db_path).parent / "feilsøking" / "feillogg.txt").read_text()


@pytest.mark.parametrize("data", [
    b"ikke en zip",
    make_zip(extra={TOP + "../utenfor.txt": "hei"}),
])
def test_bad_downloads_are_rejected(project, db_path, github, monkeypatch, data):
    monkeypatch.setattr(updater, "fetch_zip", lambda branch: data)
    with pytest.raises(updater.UpdateError):
        updater.install_latest(db_path, project_dir=project)
    assert not (project.parent / "utenfor.txt").exists()
    assert not (project / "VERSJON").exists()


def test_download_must_look_like_golflager(project, db_path, github, monkeypatch):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("noe-annet/README.md", "hei")
    monkeypatch.setattr(updater, "fetch_zip", lambda branch: buffer.getvalue())
    with pytest.raises(updater.UpdateError) as err:
        updater.install_latest(db_path, project_dir=project)
    assert "ser ikke ut som Golflager" in str(err.value)


def test_check_finds_new_version_and_shows_banner(app, client, conn, github, monkeypatch):
    app.config["VERSION"] = "1.3"
    monkeypatch.setattr(updater, "local_version", lambda project_dir=None: "1.3")
    monkeypatch.setattr(updater, "remote_version", lambda branch: "1.4")
    assert updater.check_for_update(conn) == "1.4"
    assert get_settings(conn)["update_available"] == "1.4"
    assert "En ny versjon av Golflager er klar" in client.get("/").get_data(as_text=True)
    assert "Versjon <strong>1.4</strong> er klar" in client.get("/innstillinger").get_data(
        as_text=True)

    # Innen 12 timer spør vi ikke GitHub igjen
    def fail(branch):
        raise AssertionError("skulle ikke spørre GitHub")

    monkeypatch.setattr(updater, "remote_version", fail)
    assert updater.check_for_update(conn) == "1.4"

    # Etter oppdateringen forsvinner meldingen
    app.config["VERSION"] = "1.4"
    assert "En ny versjon" not in client.get("/").get_data(as_text=True)


def test_failed_check_waits_an_hour(conn, github, monkeypatch):
    def offline(branch):
        raise updater.UpdateError("Fikk ikke kontakt med GitHub.")

    monkeypatch.setattr(updater, "remote_version", offline)
    with pytest.raises(updater.UpdateError):
        updater.check_for_update(conn)
    checked = datetime.fromisoformat(get_settings(conn)["update_checked_at"])
    next_try = checked + updater.CHECK_EVERY
    assert timedelta(minutes=55) < next_try - datetime.now() < timedelta(minutes=65)
    assert updater.check_for_update(conn) is None  # venter, spør ikke på nytt


def test_update_button_installs_and_restarts(app, client, monkeypatch):
    calls = []
    monkeypatch.setattr(updater, "install_latest", lambda database: calls.append("install") or "9.9")
    monkeypatch.setattr(updater, "restart", lambda log_path=None: calls.append("restart"))
    app.config["SHUTDOWN"] = lambda: calls.append("shutdown")
    html = client.post("/oppdater").get_data(as_text=True)
    assert "Oppdaterer til versjon 9.9" in html
    assert calls == ["install", "restart", "shutdown"]


def test_update_button_shows_errors(app, client, monkeypatch):
    def broken(database):
        raise updater.UpdateError("Fikk ikke kontakt med GitHub.")

    monkeypatch.setattr(updater, "install_latest", broken)
    response = client.post("/oppdater", follow_redirects=True)
    assert "Fikk ikke kontakt med GitHub" in response.get_data(as_text=True)


def test_status_reports_running_version(app, client):
    app.config["VERSION"] = "1.3"
    assert client.get("/api/status").get_json()["version"] == "1.3"
