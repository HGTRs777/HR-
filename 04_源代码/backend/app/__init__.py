from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, abort, current_app, send_from_directory

from .api import api_v1
from .cli import register_cli
from .config import get_config
from .errors import register_error_handlers
from .extensions import cors, db, migrate
from .logging_config import configure_logging
from .request_context import register_request_context
from .security import register_csrf_protection
from .services.policy_gaps import start_policy_gap_scheduler
from .services.embedding import start_embedding_warmup


def register_frontend(app: Flask) -> None:
    @app.get("/")
    @app.get("/<path:requested_path>")
    def frontend(requested_path: str = ""):
        if requested_path == "api" or requested_path.startswith("api/"):
            abort(404)
        if not current_app.config.get("SERVE_FRONTEND"):
            abort(404)
        dist_root = Path(current_app.config["FRONTEND_DIST_PATH"]).resolve()
        if not (dist_root / "index.html").is_file():
            abort(503, description="Vue production build is missing")
        requested_file = dist_root / requested_path
        if requested_path and requested_file.is_file():
            return send_from_directory(dist_root, requested_path)
        return send_from_directory(dist_root, "index.html")


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    configure_logging(app)
    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["FRONTEND_ORIGINS"]}},
        supports_credentials=True,
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID", "X-Client-Session-ID"],
        expose_headers=["X-Request-ID"],
    )

    register_request_context(app)
    register_csrf_protection(app)
    register_error_handlers(app)
    register_cli(app)
    app.register_blueprint(api_v1, url_prefix="/api/v1")
    register_frontend(app)
    start_embedding_warmup(app)
    start_policy_gap_scheduler(app)

    logging.getLogger(__name__).info("application initialized", extra={"app_env": app.config["APP_ENV"]})
    return app
