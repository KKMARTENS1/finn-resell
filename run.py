"""Starter Golflager og åpner den i nettleseren. Brukes av start.sh."""
from __future__ import annotations

import atexit
import logging
import os
import socket
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path
from typing import Optional


def find_free_port(start: int) -> int:
    for port in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit("Fant ingen ledig port for Golflager. Lukk noen programmer og prøv igjen.")


def running_url(url_file: Path) -> Optional[str]:
    """Adressen til en Golflager som allerede kjører, hvis det finnes en."""
    try:
        url = url_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not url.startswith("http://localhost:"):
        return None
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url + "/api/status", timeout=2) as response:
            return url if response.status == 200 else None
    except (OSError, ValueError):
        return None


def open_browser(url: str) -> None:
    if not os.environ.get("GOLFLAGER_NO_BROWSER"):
        webbrowser.open(url)


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    from werkzeug.serving import make_server

    from golflager import create_app
    from golflager.config import data_dir, db_path

    url_file = data_dir() / "server.url"
    existing = running_url(url_file)
    if existing:
        # Bare én Golflager om gangen, så scraperen ikke sjekker Finn dobbelt
        print(f"\n  ⛳  Golflager kjører allerede på {existing}. Åpner den i nettleseren.\n")
        open_browser(existing)
        return

    port = find_free_port(int(os.environ.get("GOLFLAGER_PORT", "8000")))
    app = create_app()
    server = make_server("127.0.0.1", port, app, threaded=True)
    url = f"http://localhost:{port}"
    url_file.write_text(url, encoding="utf-8")

    def cleanup() -> None:
        try:
            if url_file.read_text(encoding="utf-8").strip() == url:
                url_file.unlink()
        except OSError:
            pass

    atexit.register(cleanup)
    # Knappen «Slå av Golflager» i Innstillinger
    app.config["SHUTDOWN"] = lambda: threading.Timer(0.5, server.shutdown).start()

    print("")
    print("  ⛳  Golflager kjører!")
    print(f"      Åpne {url} i nettleseren (skjer automatisk).")
    print(f"      Dataene dine ligger i {db_path()}")
    print("")
    if sys.stdout.isatty():
        print("      La dette vinduet stå åpent mens du bruker appen.")
        print("      Trykk Ctrl + C for å stoppe.")
        print("")

    threading.Timer(1.0, lambda: open_browser(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()
    print("\n  Golflager er slått av. Ha en fin dag på banen! ⛳\n")


if __name__ == "__main__":
    main()
