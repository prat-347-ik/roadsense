import logging
import pytest
from app.core.sentry import sanitize_data_recursively, sentry_before_send, init_sentry
from app.core.config import settings


def test_sanitize_data_recursively_raw_plate():
    """Verify raw plate fields are redacted while hashed plates and other fields are preserved."""
    payload = {
        "plate_no": "MH12AB1234",
        "plate": "KA04CD5678",
        "hashed_plate": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "device_id": "cam-01",
        "nested": {
            "license_plate_no": "DL01XY9999",
            "vehicle_plate": "GJ01ZZ0001",
            "speed": 65.5,
        },
        "list_items": [
            {"plate_no": "HR26AA1111", "status": "active"},
            {"other_key": "safe_value"},
        ],
    }

    sanitized = sanitize_data_recursively(payload)

    assert sanitized["plate_no"] == "[REDACTED]"
    assert sanitized["plate"] == "[REDACTED]"
    assert sanitized["hashed_plate"] == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert sanitized["device_id"] == "cam-01"
    assert sanitized["nested"]["license_plate_no"] == "[REDACTED]"
    assert sanitized["nested"]["vehicle_plate"] == "[REDACTED]"
    assert sanitized["nested"]["speed"] == 65.5
    assert sanitized["list_items"][0]["plate_no"] == "[REDACTED]"
    assert sanitized["list_items"][0]["status"] == "active"
    assert sanitized["list_items"][1]["other_key"] == "safe_value"


def test_sentry_before_send_redaction():
    """Verify before_send strips raw plate numbers from common event sections."""
    event = {
        "event_id": "test-event-123",
        "level": "error",
        "request": {
            "data": {
                "device_id": "cam-99",
                "plate_no": "MH12AB1234",
                "violation_type": "wrong_side",
            },
            "query_string": "plate_no=MH12AB1234&device_id=cam-99",
        },
        "breadcrumbs": {
            "values": [
                {
                    "category": "auth",
                    "message": "User logged in",
                },
                {
                    "category": "burst",
                    "data": {
                        "plate_no": "MH12AB1234",
                        "raw_plate": "MH12AB1234",
                        "confidence": 0.98,
                    },
                },
            ]
        },
        "extra": {
            "last_seen_plate": "MH12AB1234",
            "hashed_plate": "abc123hash",
            "cluster_id": "cluster-7",
        },
    }

    result = sentry_before_send(event, {})

    # Request body & query sanitized
    assert result["request"]["data"]["plate_no"] == "[REDACTED]"
    assert result["request"]["data"]["device_id"] == "cam-99"

    # Breadcrumbs sanitized
    crumb_data = result["breadcrumbs"]["values"][1]["data"]
    assert crumb_data["plate_no"] == "[REDACTED]"
    assert crumb_data["raw_plate"] == "[REDACTED]"
    assert crumb_data["confidence"] == 0.98

    # Extra context sanitized
    assert result["extra"]["last_seen_plate"] == "[REDACTED]"
    assert result["extra"]["hashed_plate"] == "abc123hash"
    assert result["extra"]["cluster_id"] == "cluster-7"


def test_sentry_before_send_redacts_exception_frame_locals():
    """Verify captured local variables cannot leak a raw plate value."""
    event = {
        "exception": {
            "values": [
                {
                    "stacktrace": {
                        "frames": [
                            {
                                "vars": {
                                    "plate_no": "RAW-LOCAL-123",
                                    "hashed_plate": "abc123hash",
                                }
                            }
                        ]
                    }
                }
            ]
        }
    }

    result = sentry_before_send(event, {})

    variables = result["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]
    assert variables["plate_no"] == "[REDACTED]"
    assert variables["hashed_plate"] == "abc123hash"


def test_sentry_before_send_empty():
    assert sentry_before_send({}, {}) == {}


def test_init_sentry_noop_when_dsn_unset(monkeypatch):
    """When SENTRY_DSN is None or empty, init_sentry does nothing."""
    monkeypatch.setattr(settings, "SENTRY_DSN", None)
    # Should complete without error or side-effect
    init_sentry()


def test_init_sentry_warning_on_missing_package(monkeypatch, caplog):
    """When SENTRY_DSN is set but sentry_sdk is not importable, log a clear warning."""
    monkeypatch.setattr(settings, "SENTRY_DSN", "https://examplePublicKey@o0.ingest.sentry.io/0")
    
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "sentry_sdk":
            raise ImportError("No module named 'sentry_sdk'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    with caplog.at_level(logging.WARNING):
        init_sentry()

    assert any("SENTRY_DSN is configured, but sentry-sdk is not installed" in record.message for record in caplog.records)
