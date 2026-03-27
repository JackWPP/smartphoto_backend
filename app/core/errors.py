from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorDef:
    code: int
    message: str


ERRORS = {
    "invalid_request": ErrorDef(40001, "invalid_request"),
    "invalid_session_status": ErrorDef(40002, "invalid_session_status"),
    "invalid_platform": ErrorDef(40003, "invalid_platform"),
    "invalid_copy_field": ErrorDef(40004, "invalid_copy_field"),
    "too_many_images": ErrorDef(40005, "too_many_images"),
    "unsupported_file_type": ErrorDef(40006, "unsupported_file_type"),
    "file_too_large": ErrorDef(40007, "file_too_large"),
    "missing_required_images": ErrorDef(40008, "missing_required_images"),
    "unauthorized": ErrorDef(40101, "unauthorized"),
    "login_required": ErrorDef(40102, "login_required"),
    "forbidden": ErrorDef(40301, "forbidden"),
    "guest_trial_exhausted": ErrorDef(40302, "guest_trial_exhausted"),
    "feature_removed": ErrorDef(41001, "feature_removed"),
    "session_not_found": ErrorDef(40401, "session_not_found"),
    "job_not_found": ErrorDef(40402, "job_not_found"),
    "asset_not_found": ErrorDef(40403, "asset_not_found"),
    "user_not_found": ErrorDef(40404, "user_not_found"),
    "job_already_running": ErrorDef(40901, "job_already_running"),
    "duplicate_idempotency_key": ErrorDef(40902, "duplicate_idempotency_key"),
    "copy_validation_failed": ErrorDef(42201, "copy_validation_failed"),
    "insufficient_credits": ErrorDef(40201, "insufficient_credits"),
    "rate_limited": ErrorDef(42901, "rate_limited"),
    "internal_error": ErrorDef(50001, "internal_error"),
    "upstream_llm_error": ErrorDef(50201, "upstream_llm_error"),
    "upstream_image_error": ErrorDef(50202, "upstream_image_error"),
    "queue_unavailable": ErrorDef(50301, "queue_unavailable"),
}


class AppError(Exception):
    def __init__(self, key: str, message: str | None = None, http_status: int = 400, retryable: bool = False):
        if key not in ERRORS:
            key = "internal_error"
        self.key = key
        self.error = ERRORS[key]
        self.message = message or self.error.message
        self.http_status = http_status
        self.retryable = retryable
        super().__init__(self.message)
