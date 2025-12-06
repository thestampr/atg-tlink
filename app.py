import os
from pathlib import Path
from typing import Optional, Tuple

from werkzeug.serving import make_ssl_devcert

from app import create_app

app = create_app()


def _env_true(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


def _resolve_ssl_context() -> Optional[Tuple[str, str]]:
    """Find or lazily create a self-signed cert for local HTTPS."""

    cert_file = os.getenv("SSL_CERT_FILE")
    key_file = os.getenv("SSL_KEY_FILE")

    if cert_file and key_file:
        cert_path = Path(cert_file)
        key_path = Path(key_file)
        if cert_path.exists() and key_path.exists():
            return str(cert_path), str(key_path)

    if not _env_true("SSL_AUTO_GENERATE", "true"):
        return None

    base_dir = Path(os.getenv("SSL_CERT_DIR", "instance/certs"))
    base_dir.mkdir(parents=True, exist_ok=True)
    base = base_dir / "localhost"
    cert_path = base.with_suffix(".crt")
    key_path = base.with_suffix(".key")

    if not (cert_path.exists() and key_path.exists()):
        make_ssl_devcert(str(base), host="localhost")

    return str(cert_path), str(key_path)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "3000"))
    use_https = _env_true("USE_HTTPS", "true")
    ssl_context = _resolve_ssl_context() if use_https else None

    if ssl_context:
        app.logger.info("Starting HTTPS server on port %s", port)
    elif use_https:
        app.logger.warning("SSL context missing; falling back to HTTP on port %s", port)
    else:
        app.logger.info("USE_HTTPS disabled; starting HTTP server on port %s", port)

    app.run(host="0.0.0.0", port=port, ssl_context=ssl_context, debug=app.config["DEBUG"])
