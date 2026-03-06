from pydantic import BaseModel


class APIResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: dict | list | None
