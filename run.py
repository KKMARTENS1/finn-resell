"""Starter Golflager og åpner den i nettleseren. Brukes av start.sh."""
from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import webbrowser


def find_free_port(start: int) -> int:
    for port in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit("Fant ingen ledig port for Golflager. Lukk noen programmer og prøv igjen.")


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    from werkzeug.serving import make_server

    from golflager import create_app
    from golflager.config import db_path

    port = find_free_port(int(os.environ.get("GOLFLAGER_PORT", "8000")))
    app = create_app()
    server = make_server("127.0.0.1", port, app, threaded=True)
    url = f"http://localhost:{port}"

    print("")
    print("  ⛳  Golflager kjører!")
    print(f"      Åpne {url} i nettleseren (skjer automatisk).")
    print(f"      Dataene dine ligger i {db_path()}")
    print("")
    print("      La dette vinduet stå åpent mens du bruker appen.")
    print("      Trykk Ctrl + C for å stoppe.")
    print("")

    if not os.environ.get("GOLFLAGER_NO_BROWSER"):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Golflager er stoppet. Ha en fin dag på banen! ⛳\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
