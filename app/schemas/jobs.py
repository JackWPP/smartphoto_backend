from pydantic import BaseModel


class JobStatusResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    progress: int
    stage: str | None
    estimated_seconds: int | None = None
    error_code: str | None = None
    error_message: str | None = None
