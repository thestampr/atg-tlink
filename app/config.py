import os
from pathlib import Path
from typing import List


class Config:
    """Reads runtime settings from environment variables."""

    DEBUG = os.getenv("DEBUG", "false").lower() in {"1", "true", "yes"}

    BASE_DIR = Path(__file__).resolve().parent.parent

    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    DATABASE_URL = os.getenv(
        "DATABASE_URL", "mysql://tlink:tlinkpass@localhost:3306/tlink"
    )
    SCHEMA_PATH = os.getenv("SCHEMA_PATH", str(BASE_DIR / "sql" / "schema.sql"))
    DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
    AUTO_APPLY_SCHEMA = os.getenv("AUTO_APPLY_SCHEMA", "true").lower() in {"1", "true", "yes"}
    USE_HTTPS = os.getenv("USE_HTTPS", "true").lower() in {"1", "true", "yes"}

    PUSH_WEBHOOK_SECRET = os.getenv("PUSH_WEBHOOK_SECRET", "")
    DEFAULT_PAGE_SIZE = int(os.getenv("DEFAULT_PAGE_SIZE", "25"))
    MAX_PAGE_SIZE = int(os.getenv("MAX_PAGE_SIZE", "100"))
    HISTORY_LIMIT = int(os.getenv("DEFAULT_HISTORY_LIMIT", "50"))
    LOG_AGE = int(os.getenv("LOG_AGE", "90"))
    SYNC_LOG_DIR = os.getenv("SYNC_LOG_DIR", str(BASE_DIR / "logs"))
    REGISTER_FORM_POST_URL = os.getenv("REGISTER_FORM_POST_URL", "/api/users/register")
    REGISTER_FORM_DEVICE_LIMIT = int(os.getenv("REGISTER_FORM_DEVICE_LIMIT", "50"))

    _cors = os.getenv("CORS_ALLOWED_ORIGINS", "*")
    CORS_ALLOWED_ORIGINS: List[str] = [o.strip() for o in _cors.split(",") if o.strip()]

    API_DOC_SOURCE = str(BASE_DIR / "docs" / "official_api_reference.md")

    TLINK_BASE_URL = os.getenv("TLINK_BASE_URL", "https://app.dtuip.com").rstrip("/")
    TLINK_SENSOR_DATA_PATH = "/api/device/getDeviceSensorDatas"
    TLINK_SENSOR_HTTP_METHOD = "GET"
    TLINK_ACCOUNT_NUMBER = int(os.getenv("TLINK_ACCOUNT_NUMBER", "0"))
    TLINK_APP_ID = os.getenv("TLINK_APP_ID", "")
    TLINK_HTTP_TIMEOUT = int(os.getenv("TLINK_HTTP_TIMEOUT", "30"))
    TLINK_OAUTH_TOKEN_URL = os.getenv("TLINK_OAUTH_TOKEN_URL", "https://app.dtuip.com/oauth/token")
    TLINK_OAUTH_CLIENT_ID = os.getenv("TLINK_OAUTH_CLIENT_ID", "")
    TLINK_OAUTH_CLIENT_SECRET = os.getenv("TLINK_OAUTH_CLIENT_SECRET", "")
    TLINK_OAUTH_USERNAME = os.getenv("TLINK_OAUTH_USERNAME", "")
    TLINK_OAUTH_PASSWORD = os.getenv("TLINK_OAUTH_PASSWORD", "")
    TLINK_OAUTH_SCOPE = os.getenv("TLINK_OAUTH_SCOPE", "")
    TLINK_OAUTH_REFRESH_BUFFER = int(os.getenv("TLINK_OAUTH_REFRESH_BUFFER", "60"))
    TLINK_SYNC_ENABLED = os.getenv("TLINK_SYNC_ENABLED", "true").lower() in {"1", "true", "yes"}
    TLINK_SYNC_INTERVAL_SECONDS = int(os.getenv("TLINK_SYNC_INTERVAL_SECONDS", "60"))
    TLINK_SYNC_PAGE_SIZE = int(os.getenv("TLINK_SYNC_PAGE_SIZE", "10"))
