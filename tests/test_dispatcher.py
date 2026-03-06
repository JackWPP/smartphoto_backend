from types import SimpleNamespace

from app.services import dispatcher


def test_dispatch_job_uses_configured_celery_app(monkeypatch):
    sent: dict[str, object] = {}

    monkeypatch.setattr(dispatcher, "get_settings", lambda: SimpleNamespace(tasks_eager=False))
    monkeypatch.setattr(
        dispatcher.execute_job,
        "apply_async",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("apply_async should not be used")),
    )

    def fake_send_task(name: str, args: list[str], queue: str) -> None:
        sent["name"] = name
        sent["args"] = args
        sent["queue"] = queue

    monkeypatch.setattr(dispatcher.celery_app, "send_task", fake_send_task)

    dispatcher.dispatch_job("job-123", queue="q.analysis")

    assert sent == {
        "name": dispatcher.execute_job.name,
        "args": ["job-123"],
        "queue": "q.analysis",
    }


def test_dispatch_job_runs_inline_when_tasks_eager(monkeypatch):
    called: dict[str, str] = {}

    monkeypatch.setattr(dispatcher, "get_settings", lambda: SimpleNamespace(tasks_eager=True))
    monkeypatch.setattr(
        dispatcher.celery_app,
        "send_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("send_task should not be used")),
    )
    monkeypatch.setattr(dispatcher, "execute_job", lambda job_id: called.setdefault("job_id", job_id))

    dispatcher.dispatch_job("job-inline", queue="q.analysis")

    assert called == {"job_id": "job-inline"}
