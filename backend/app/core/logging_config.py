import logging
import re
from typing import Any


class PlateRedactionFilter(logging.Filter):
    """Logging filter that ensures raw license plates never leak into log output."""

    # Regex to catch explicit mentions like plate_no=XYZ or raw plate formats
    PLATE_PATTERN = re.compile(r"(?:plate_no['\":\s=]+)(['\"][^'\"]+['\"]|[^\s,}{]+)", re.IGNORECASE)

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.PLATE_PATTERN.sub("plate_no=[REDACTED]", record.msg)
        if record.args:
            if isinstance(record.args, dict):
                sanitized = {}
                for k, v in record.args.items():
                    if "plate" in k.lower() and not k.startswith("hashed_"):
                        sanitized[k] = "[REDACTED]"
                    else:
                        sanitized[k] = v
                record.args = sanitized
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(
                    "[REDACTED]" if isinstance(a, str) and len(a) <= 16 and a.isalnum() else a
                    for a in record.args
                )
        return True


def setup_logging() -> None:
    """Configure structured and privacy-preserving logging."""
    logger = logging.getLogger("roadsense")
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    handler.setFormatter(formatter)
    handler.addFilter(PlateRedactionFilter())

    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False


setup_logging()
logger = logging.getLogger("roadsense")
