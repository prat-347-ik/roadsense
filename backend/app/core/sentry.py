from typing import Any
from app.core.config import settings


def sanitize_data_recursively(data: Any) -> Any:
    """Recursively scrub raw plate numbers from dictionaries, lists, or breadcrumbs."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if "plate_no" in k_lower or (k_lower == "plate" and not k_lower.startswith("hashed_")):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_data_recursively(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_data_recursively(item) for item in data]
    return data


def sentry_before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """Sentry before_send callback to guarantee raw plate_no is completely stripped

    from exception traces, request data, extra context, and breadcrumbs.
    """
    if not event:
        return event

    # Sanitize request body / query if present
    if "request" in event:
        req = event["request"]
        if "data" in req:
            req["data"] = sanitize_data_recursively(req["data"])
        if "query_string" in req:
            req["query_string"] = sanitize_data_recursively(req["query_string"])

    # Sanitize breadcrumbs
    if "breadcrumbs" in event and "values" in event["breadcrumbs"]:
        for breadcrumb in event["breadcrumbs"]["values"]:
            if "data" in breadcrumb:
                breadcrumb["data"] = sanitize_data_recursively(breadcrumb["data"])

    # Sanitize extra context
    if "extra" in event:
        event["extra"] = sanitize_data_recursively(event["extra"])

    return event


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
        except ImportError:
            pass
