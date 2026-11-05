from typing import Any


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 422, **details: Any) -> None:
        self.code = code
        self.message = message
        self.status = status
        self.details = details
        super().__init__(message)

    def payload(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.details}


class TransientError(Exception):
    def __init__(self, code: str, retry_after: float | None = None) -> None:
        self.code = code
        self.retry_after = retry_after
        super().__init__(code)
