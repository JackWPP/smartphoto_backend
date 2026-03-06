from typing import Any


def success_response(data: Any) -> dict[str, Any]:
    return {"code": 0, "message": "success", "data": data}


def error_response(code: int, message: str, data: Any = None) -> dict[str, Any]:
    return {"code": code, "message": message, "data": data}
