import hmac
import json
import os
from typing import Any


def cors_headers() -> dict[str, str]:
    # Lambda Function URL CORS config (CDK) adds Access-Control-* headers automatically.
    # Returning them here too would create duplicates, which browsers reject.
    return {"Content-Type": "application/json"}


def error_response(status: int, message: str) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": cors_headers(),
        "body": json.dumps({"error": message}),
    }


def is_options_request(event: dict[str, Any]) -> bool:
    return (event.get("requestContext") or {}).get("http", {}).get("method") == "OPTIONS"


def options_response() -> dict[str, Any]:
    return {"statusCode": 204, "headers": cors_headers(), "body": ""}


def _headers(event: dict[str, Any]) -> dict[str, Any]:
    return {str(k).lower(): v for k, v in (event.get("headers") or {}).items()}


def _request_token(event: dict[str, Any]) -> str:
    headers = _headers(event)
    auth = str(headers.get("authorization") or "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return str(headers.get("x-app-token") or "").strip()


def _is_local_or_test() -> bool:
    env = (
        os.environ.get("APP_ENV")
        or os.environ.get("ENVIRONMENT")
        or os.environ.get("ENV")
        or os.environ.get("STAGE")
        or ""
    ).strip().lower()
    if env:
        return env in {"local", "dev", "development", "test"}

    return not (
        os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
        or os.environ.get("DB_SECRET_ARN")
    )


def auth_error(event: dict[str, Any], *, allow_non_http: bool = False) -> dict[str, Any] | None:
    if allow_non_http and not event.get("headers") and not event.get("requestContext"):
        return None

    expected = os.environ.get("APP_AUTH_TOKEN", "").strip()
    if not expected:
        if _is_local_or_test():
            return None
        return error_response(503, "APP_AUTH_TOKEN is not configured")

    if not hmac.compare_digest(_request_token(event), expected):
        return error_response(401, "Unauthorized")

    return None
