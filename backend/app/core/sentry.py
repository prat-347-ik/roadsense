import logging
from typing import Any
from app.core.config import settings

logger = logging.getLogger(__name__)


def sanitize_data_recursively(data: Any) -> Any:
    """Recursively scrub raw plate numbers from dictionaries, lists, or breadcrumbs."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if "plate" in k_lower and not k_lower.startswith("hashed_"):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_data_recursively(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_data_recursively(item) for item in data]
    return data


def sentry_before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """Redact raw plate values from every nested part of a Sentry event."""
    if not event:
        return event

    return sanitize_data_recursively(event)


def init_sentry() -> None:
    """Initialize Sentry integration if SENTRY_DSN is configured."""
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk

            sentry_sdk.init(
                dsn=settings.SENTRY_DSN,
                before_send=sentry_before_send,
                send_default_pii=False,
                traces_sample_rate=0.1,
            )
            logger.info("Sentry error tracking initialized successfully.")
        except ImportError:
            logger.warning(
                "SENTRY_DSN is configured, but sentry-sdk is not installed. "
                "Error tracking is disabled. Run: pip install 'sentry-sdk>=2.0.0'"
            )
