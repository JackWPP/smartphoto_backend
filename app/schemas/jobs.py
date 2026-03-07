from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class JobStatusData(BaseModel):
    job_id: str = Field(description="任务 ID。")
    job_type: str = Field(description="任务类型。")
    status: str = Field(description="任务状态。")
    progress: int = Field(description="进度百分比。", examples=[80])
    stage: str | None = Field(default=None, description="当前阶段。")
    estimated_seconds: int | None = Field(default=None, description="预估剩余秒数。当前未实现。")
    error_code: str | None = Field(default=None, description="失败时的业务错误码。")
    error_message: str | None = Field(default=None, description="失败时的错误消息。")


class JobEventSSEPayload(BaseModel):
    event: str | None = Field(default=None, description="事件名。")
    payload: dict[str, Any] | None = Field(default=None, description="SSE 事件数据。")
