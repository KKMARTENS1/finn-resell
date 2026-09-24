"""Vennlig feilside og feillogg, så en feil aldri stopper hele appen."""
from __future__ import annotations

import logging
import traceback
from datetime import datetime
from html import escape
from pathlib import Path

from flask import Flask, request

log = logging.getLogger(__name__)
MAX_LOG_BYTES = 200_000

PAGE = """<!doctype html>
<html lang="no"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Noe gikk galt · Golflager</title>
<link rel="stylesheet" href="/static/style.css"></head>
<body><main class="main" style="margin:0 auto; max-width:720px">
  <div class="card" style="margin-top:40px">
    <h1>Noe gikk galt på denne siden</h1>
    <p style="margin:12px 0">Resten av appen virker som regel fortsatt. Dataene dine er trygge.</p>
    <p style="margin:12px 0">Feilen er lagret i <code>{log_file}</code>. Send gjerne den filen, eller teksten under,
      til den som laget appen, så blir det fikset.</p>
    <pre style="white-space:pre-wrap; background:var(--surface-2); padding:12px; border-radius:9px; font-size:13px">{error}</pre>
    <p style="margin-top:18px; display:flex; gap:8px; flex-wrap:wrap">
      <a class="btn btn--primary" href="/">Gå til Oversikt</a>
      <a class="btn" href="/sok">Finn-søk</a>
      <a class="btn" href="/lager">Lager</a>
    </p>
  </div>
</main></body></html>"""


def _write_log(log_file: Path, text: str) -> None:
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        if log_file.exists() and log_file.stat().st_size > MAX_LOG_BYTES:
            log_file.write_text(log_file.read_text(encoding="utf-8")[-MAX_LOG_BYTES // 2:],
                                encoding="utf-8")
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
        log.warning("Klarte ikke å skrive feilloggen %s", log_file)


def register_error_page(app: Flask) -> None:
    log_file = Path(app.config["DATABASE"]).parent / "feilsøking" / "feillogg.txt"

    @app.errorhandler(500)
    def internal_error(error):  # noqa: ANN001
        original = getattr(error, "original_exception", None) or error
        details = "".join(traceback.format_exception(type(original), original,
                                                     original.__traceback__))
        _write_log(log_file, f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} {request.method} "
                             f"{request.full_path}\n{details}")
        summary = f"{request.path}: {type(original).__name__}: {original}"
        return PAGE.format(log_file=escape(str(log_file)), error=escape(summary)), 500
