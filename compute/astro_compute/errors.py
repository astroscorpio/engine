from __future__ import annotations


class ApiError(Exception):
    """An error with a contract code; rendered as {"error": {...}}."""

    def __init__(self, code: str, message: str, status: int = 400, field: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.field = field

    def body(self) -> dict:
        err = {"code": self.code, "message": self.message}
        if self.field:
            err["field"] = self.field
        return {"error": err}


def invalid(message: str, field: str | None = None) -> ApiError:
    return ApiError("invalid_input", message, 400, field)


def unsupported_location(message: str) -> ApiError:
    return ApiError("unsupported_location", message, 422)
