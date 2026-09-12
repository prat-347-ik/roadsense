from typing import Any
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Custom validation error handler.

    Guarantees that invalid `plate_no` inputs are NEVER echoed back in error responses.
    """
    sanitized_errors: list[dict[str, Any]] = []

    for err in exc.errors():
        loc = err.get("loc", ())
        is_plate_field = any("plate" in str(elem).lower() for elem in loc)

        if is_plate_field:
            # Redact raw input and provide standard generic message
            sanitized_errors.append(
                {
                    "loc": loc,
                    "msg": "invalid plate_no format",
                    "type": "value_error",
                }
            )
        else:
            # Copy error detail while scrubbing input if sensitive
            error_copy = dict(err)
            if "input" in error_copy and isinstance(error_copy["input"], dict):
                input_copy = dict(error_copy["input"])
                for k in list(input_copy.keys()):
                    if "plate" in k.lower():
                        input_copy[k] = "[REDACTED]"
                error_copy["input"] = input_copy
            sanitized_errors.append(error_copy)

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": sanitized_errors},
    )
