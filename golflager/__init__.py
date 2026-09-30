"""Golflager: dashbord for kjøp og salg av brukt golfutstyr fra Finn.no."""
from __future__ import annotations

from typing import Optional

from flask import Flask

from . import db
from .config import db_path
from .errors import register_error_page
from .formatting import register_filters


def create_app(database: Optional[str] = None, start_scraper: bool = True) -> Flask:
    app = Flask(__name__)
    app.config["DATABASE"] = str(database or db_path())
    db.init_db(app.config["DATABASE"])
    conn = db.connect(app.config["DATABASE"])
    try:
        app.config["SECRET_KEY"] = db.get_raw_setting(conn, "secret_key")
    finally:
        conn.close()
    app.config["TEMPLATES_AUTO_RELOAD"] = False
    from .updater import local_version

    app.config["VERSION"] = local_version()

    from .scraper import ScraperWorker
    from .views import bp

    app.register_blueprint(bp)
    register_filters(app)
    register_error_page(app)
    worker = ScraperWorker(app.config["DATABASE"])
    app.extensions["scraper"] = worker
    if start_scraper:
        worker.start()
    return app
