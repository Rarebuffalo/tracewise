"""T-706 operational events: names, correlation ids, field sanitising, redaction, and never-raise."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

import pytest

from tracewise import observe
from tracewise.logging import JsonFormatter, SecretFilter
from tracewise.observe import Stages, bind, event, sanitize

log = logging.getLogger("tests.observe")


def test_sanitize_drops_credential_and_content_fields_by_word_and_keeps_metrics() -> None:
    out = sanitize(
        {
            "authorization": "Bearer x",
            "api_token": "t",
            "log_url": "https://x",
            "signed_url": "https://y",
            "body": "b",
            "patch": "p",
            "source_text": "s",
            "error_message": "m",
            "jwt": "j",
            "tokens_in": 10,
            "tokens_out": 2,
            "context_kind": "git",
            "outcome": "diagnosed",
            "abstained": False,
            "rate": 0.5,
            "flags": ["a", "b"],
            "stage_ms": {"collect": 3, "headers": "h"},
            "obj": object(),
            "mixed": ["a", object()],
        }
    )
    assert out == {
        "tokens_in": 10,
        "tokens_out": 2,
        "context_kind": "git",
        "outcome": "diagnosed",
        "abstained": False,
        "rate": 0.5,
        "flags": ["a", "b"],
        "stage_ms": {"collect": 3},
    }


def test_strings_and_lists_are_bounded() -> None:
    out = sanitize({"reason": "x" * 1000, "flags": list(range(100))})
    assert len(out["reason"]) == observe.MAX_STR and len(out["flags"]) == observe.MAX_LIST


def test_event_carries_name_bound_ids_and_fields(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    with bind(job_id=5, installation_id=9), bind(repo_id=7, run_id=55, not_an_id=1, attempt=True):  # type: ignore[arg-type]
        event(log, "job.claimed", kind="analyze", event="spoofed")
    (rec,) = [r for r in caplog.records if r.getMessage() == "job.claimed"]
    assert rec.tw == {"job_id": 5, "installation_id": 9, "repo_id": 7, "run_id": 55, "kind": "analyze", "event": "job.claimed"}
    event(log, "job.claimed")  # ids are unbound after the context
    assert caplog.records[-1].tw == {"event": "job.claimed"}


def test_bound_ids_are_thread_local() -> None:
    seen: dict[str, Any] = {}

    def other() -> None:
        seen["ids"] = observe.current_ids()

    with bind(job_id=1):
        t = threading.Thread(target=other)
        t.start()
        t.join()
    assert seen["ids"] == {}


def test_json_line_is_scrubbed_and_includes_ids() -> None:
    f = SecretFilter()
    f.register("very-secret-value")
    lg = logging.getLogger("tests.observe.json")
    lines: list[str] = []

    class H(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(self.format(record))

    h = H()
    h.setFormatter(JsonFormatter())
    h.addFilter(f)
    lg.addHandler(h)
    lg.setLevel(logging.INFO)
    try:
        with bind(delivery_id="d-1"):
            event(lg, "webhook.ingested", outcome="very-secret-value", reason="ghs_" + "a" * 36)
    finally:
        lg.removeHandler(h)
    doc = json.loads(lines[0])
    assert doc["event"] == doc["msg"] == "webhook.ingested" and doc["delivery_id"] == "d-1"
    assert "very-secret-value" not in lines[0] and "ghs_aaaa" not in lines[0]


def test_event_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    before = observe.dropped_events
    event(log, "Not A Valid Name")

    class Broken(logging.Logger):
        def log(self, *a: Any, **k: Any) -> None:  # type: ignore[override]
            raise RuntimeError("handler down")

    event(Broken("x"), "job.claimed")
    monkeypatch.setattr(observe, "sanitize", lambda f: (_ for _ in ()).throw(ValueError("boom")))
    event(log, "job.claimed", x=1)
    assert observe.dropped_events == before + 3


def test_stages_accumulate_with_a_fake_clock() -> None:
    t = iter([0.0, 0.25, 1.0, 1.5, 2.0, 2.0])
    s = Stages(clock=lambda: next(t))
    with s.time("collect"):
        pass
    with s.time("diagnose"):
        pass
    with pytest.raises(KeyError), s.time("collect"):
        raise KeyError("still timed")
    assert s.ms == {"collect": 250, "diagnose": 500}
