from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    code: int = Field(default=0, description="业务状态码。成功固定为 0。", examples=[0])
    message: str = Field(default="success", description="业务消息。成功固定为 success。", examples=["success"])
    data: T = Field(description="接口返回的业务数据。")


class APIErrorResponse(BaseModel):
    code: int = Field(description="业务错误码，如 40002 / 40901 / 50202。", examples=[40002])
    message: str = Field(description="错误描述。", examples=["invalid_session_status"])
    data: Any | None = Field(default=None, description="错误附加数据。当前多数场景为空。")


OPENAPI_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": APIErrorResponse, "description": "业务校验失败，例如状态不合法、参数缺失、平台无效。"},
    401: {"model": APIErrorResponse, "description": "未认证。当前开发态通常不会出现。"},
    403: {"model": APIErrorResponse, "description": "无权限访问该资源。"},
    404: {"model": APIErrorResponse, "description": "资源不存在，例如 session/job/asset 不存在。"},
    409: {"model": APIErrorResponse, "description": "并发冲突或幂等冲突，例如 40901 / 40902。"},
    410: {"model": APIErrorResponse, "description": "能力已下线，当前仓库不再提供该功能。"},
    422: {"model": APIErrorResponse, "description": "请求体或表单参数未通过 FastAPI/Pydantic 校验。"},
    500: {"model": APIErrorResponse, "description": "服务内部异常。"},
    502: {"model": APIErrorResponse, "description": "上游 LLM 或生图服务异常，例如 50201 / 50202。"},
}
