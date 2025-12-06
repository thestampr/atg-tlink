import os
from pathlib import Path
from typing import Dict, List


def _csv_to_ints(value: str) -> List[int]:
    result: List[int] = []
    for token in (value or "").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            result.append(int(token))
        except ValueError:
            continue
    return result


def _csv_to_str_map(value: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for token in (value or "").split(","):
        token = token.strip()
        if not token or ":" not in token:
            continue
        key, _, val = token.partition(":")
        key = key.strip()
        if not key:
            continue
        mapping[key] = val.strip()
    return mapping


def _csv_to_float_map(value: str) -> Dict[str, float]:
    mapping: Dict[str, float] = {}
    for key, val in _csv_to_str_map(value).items():
        try:
            mapping[key.lower()] = float(val)
        except ValueError:
            continue
    return mapping


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

    ATG_EXPORT_ENABLED = os.getenv("ATG_EXPORT_ENABLED", "true").lower() in {"1", "true", "yes"}
    ATG_EXPORT_ENDPOINT = os.getenv(
        "ATG_EXPORT_ENDPOINT", "https://supsopha.com/api/upload_atg_record.php"
    )
    ATG_EXPORT_TIMEOUT = int(os.getenv("ATG_EXPORT_TIMEOUT", "10"))
    ATG_EXPORT_SENSOR_IDS = _csv_to_ints(os.getenv("ATG_EXPORT_SENSOR_IDS", ""))
    ATG_EXPORT_WIDTH_CM = float(os.getenv("ATG_EXPORT_WIDTH_CM", "155"))
    ATG_EXPORT_HEIGHT_CM = float(os.getenv("ATG_EXPORT_HEIGHT_CM", "155"))
    ATG_EXPORT_SHORT_LENGTH_CM = float(os.getenv("ATG_EXPORT_SHORT_LENGTH_CM", "246"))
    ATG_EXPORT_LONG_LENGTH_CM = float(os.getenv("ATG_EXPORT_LONG_LENGTH_CM", "492"))
    ATG_EXPORT_LONG_SENSOR_IDS = set(
        _csv_to_ints(os.getenv("ATG_EXPORT_LONG_SENSOR_IDS", "6026176"))
    )
    ATG_EXPORT_WALL_THICKNESS_CM = float(os.getenv("ATG_EXPORT_WALL_THICKNESS_CM", "0.6"))
    ATG_EXPORT_DEFAULT_OIL_TYPE = os.getenv("ATG_EXPORT_DEFAULT_OIL_TYPE", "Gasoline")
    ATG_EXPORT_SENSOR_OIL_TYPES = _csv_to_str_map(
        os.getenv("ATG_EXPORT_SENSOR_OIL_TYPES", "6026176:Diesel")
    )
    ATG_EXPORT_DEFAULT_DENSITY = float(os.getenv("ATG_EXPORT_DEFAULT_DENSITY", "0.75"))
    ATG_EXPORT_OIL_DENSITIES = _csv_to_float_map(
        os.getenv("ATG_EXPORT_OIL_DENSITIES", "diesel:0.84,gasoline:0.75")
    )
    ATG_EXPORT_CONNECT_TTL_SECONDS = int(os.getenv("ATG_EXPORT_CONNECT_TTL_SECONDS", "900"))
    ATG_EXPORT_DEFAULT_TEMPERATURE = float(os.getenv("ATG_EXPORT_DEFAULT_TEMPERATURE", "30"))
