from app.core.errors import AppError

SESSION_TRANSITIONS: dict[str, set[str]] = {
    "created": {"images_uploaded"},
    "images_uploaded": {"analyzing", "platform_selected"},
    "analyzing": {"analyzed", "failed"},
    "analyzed": {"platform_selected", "copy_ready", "failed"},
    "platform_selected": {"analyzing", "copy_ready", "failed"},
    "copy_ready": {"analyzing", "strategy_ready", "failed"},
    "strategy_ready": {"analyzing", "generating", "failed"},
    "generating": {"completed", "failed"},
    "completed": {"analyzing", "generating", "completed", "failed"},
    "failed": {"analyzing", "copy_ready", "strategy_ready", "generating"},
}

RUNNING_JOB_STATES = {"queued", "running"}


def ensure_session_transition(old_status: str, new_status: str) -> None:
    allowed = SESSION_TRANSITIONS.get(old_status, set())
    if old_status == new_status:
        return
    if new_status not in allowed:
        raise AppError("invalid_session_status", f"cannot transition {old_status} -> {new_status}", 400)
