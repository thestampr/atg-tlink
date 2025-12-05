from dotenv import load_dotenv

load_dotenv(".env")

from flask import Flask
from flask_cors import CORS

from .config import Config
from .db import init_app as init_db
from .tasks import init_task_scheduler


def create_app() -> Flask:
    """Application factory that wires configuration, database, and blueprints."""

    app = Flask(__name__)
    app.config.from_object(Config())
    init_db(app)
    init_task_scheduler(app)

    CORS(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ALLOWED_ORIGINS"]}},
        supports_credentials=False,
    )

    from .routes import api_bp  # local import to avoid circular dependency

    app.register_blueprint(api_bp, url_prefix="/api")
    app.logger.setLevel("DEBUG" if app.config["DEBUG"] else "INFO")

    return app
