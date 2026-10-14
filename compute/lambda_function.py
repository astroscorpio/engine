"""AWS Lambda entry point (Function URL, payload format 2.0)."""

from __future__ import annotations

import base64
import logging

from astro_compute.app import dumps, handle, query_dict

logging.getLogger().setLevel(logging.INFO)

HEADERS = {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"}


def handler(event, context):
    http = event.get("requestContext", {}).get("http", {})
    body = event.get("body")
    if body and event.get("isBase64Encoded"):
        body = base64.b64decode(body)
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    status, payload = handle(
        http.get("method", "GET"),
        event.get("rawPath", "/"),
        query_dict(event.get("rawQueryString", "")),
        body,
        headers,
    )
    return {"statusCode": status, "headers": HEADERS, "body": dumps(payload)}
