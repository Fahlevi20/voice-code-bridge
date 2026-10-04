import argparse
import json
from types import SimpleNamespace

import numpy as np
import pytest

from voice_code.__main__ import main, session_uuid
from voice_code.audio import EndpointConfig, SpeechEndpoint
from voice_code.cli_adapter import ClaudeAdapter, CliError, ResumeError
from voice_code.controller import VoiceController


def test_endpoint_submits_after_silence_once():
    config = EndpointConfig(block_seconds=0.1, sample_rate=100,
                            silence_seconds=0.3, min_speech_seconds=0.2,
                            threshold=0.1)
    endpoint = SpeechEndpoint(config)
    silence = np.zeros(10, dtype=np.float32)
    speech = np.full(10, 0.5, dtype=np.float32)
    assert endpoint.feed(silence) is None
    assert endpoint.feed(speech) is None
    assert endpoint.feed(speech) is None
    assert endpoint.feed(silence) is None
    assert endpoint.feed(silence) is None
    audio = endpoint.feed(silence)
    assert audio is not None and len(audio) >= 50
    assert endpoint.feed(silence) is None


def test_endpoint_discards_short_noise():
    config = EndpointConfig(block_seconds=0.1, sample_rate=100,
                            silence_seconds=0.2, min_speech_seconds=0.3,
                            threshold=0.1)
    endpoint = SpeechEndpoint(config)
    assert endpoint.feed(np.ones(10, dtype=np.float32)) is None
    assert endpoint.feed(np.zeros(10, dtype=np.float32)) is None
    assert endpoint.feed(np.zeros(10, dtype=np.float32)) is None


def test_cli_resumes_and_reports_denials(tmp_path):
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        payload = {"result": "Done", "session_id": "session-123",
                   "permission_denials": [{"tool_name": "Edit"}]}
        return SimpleNamespace(stdout=json.dumps(payload), returncode=0)

    adapter = ClaudeAdapter(str(tmp_path), base_url="http://localhost:12345", model="example-model",
                            auth_token="example-test-token", executable="claude", runner=runner)
    assert "denied" in adapter.ask("first")
    adapter.ask("second")
    assert "--resume" not in calls[0][0]
    assert calls[1][0][-2:] == ["--resume", "session-123"]
    assert "--dangerously-skip-permissions" not in calls[0][0]
    assert calls[0][1]["env"]["ANTHROPIC_AUTH_TOKEN"] == "example-test-token"
    assert "example-test-token" not in repr(calls[0][0])
    assert calls[0][1]["encoding"] == "utf-8"
    assert calls[0][1]["errors"] == "replace"


def test_cli_invalid_json(tmp_path):
    adapter = ClaudeAdapter(str(tmp_path), executable="claude",
                            runner=lambda *a, **k: SimpleNamespace(stdout="not json", returncode=1))
    try:
        adapter.ask("hello")
    except CliError as exc:
        assert "JSON" in str(exc)
    else:
        assert False, "expected CliError"


def test_controller_speaks_entire_answer_once(capsys):
    calls = []
    answer = "First sentence. Second sentence. Some code: print('hello')."
    transcriber = SimpleNamespace(transcribe=lambda audio: "build a page")
    adapter = SimpleNamespace(ask=lambda prompt: calls.append(("ask", prompt)) or answer)
    controller = VoiceController(EndpointConfig(), transcriber, adapter,
                                 listener=lambda *args: calls.append(("listen",)) or np.ones(10),
                                 speaker=lambda text: calls.append(("speak", text)))
    controller.once()
    assert calls == [("listen",), ("ask", "build a page"), ("speak", answer)]
    assert answer in capsys.readouterr().out


def test_explicit_resume_first_turn_and_followups(tmp_path):
    session_id = "550e8400-e29b-41d4-a716-446655440000"
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=json.dumps({"result": "I remember", "session_id": session_id}),
                               returncode=0)

    adapter = ClaudeAdapter(str(tmp_path), executable="claude", runner=runner,
                            session_id=session_id)
    assert adapter.ask("first") == "I remember"
    assert adapter.ask("second") == "I remember"
    assert calls[0][-2:] == ["--resume", session_id]
    assert calls[1][-2:] == ["--resume", session_id]


def test_resume_errors_are_fatal(tmp_path):
    session_id = "550e8400-e29b-41d4-a716-446655440000"
    for payload, code in [("not json", 1),
                          (json.dumps({"result": "No conversation found", "is_error": True}), 1),
                          (json.dumps({"result": "wrong", "session_id": "different-id"}), 0)]:
        adapter = ClaudeAdapter(str(tmp_path), executable="claude", session_id=session_id,
                                runner=lambda *a, **k: SimpleNamespace(stdout=payload, returncode=code))
        with pytest.raises(ResumeError):
            adapter.ask("hello")
        assert adapter.session_id == session_id


def test_controller_stops_after_resume_error(capsys):
    calls = []

    def listener(config, device):
        calls.append("listen")
        return np.ones(10)

    def fail(prompt):
        raise ResumeError("not available")

    controller = VoiceController(EndpointConfig(), SimpleNamespace(transcribe=lambda audio: "hello"),
                                 SimpleNamespace(ask=fail), listener=listener)
    controller.run()
    assert calls == ["listen"]
    assert "Session handoff stopped" in capsys.readouterr().out


def test_uuid_validation_and_dry_run_conflict(monkeypatch):
    session_id = "550e8400-e29b-41d4-a716-446655440000"
    assert session_uuid(session_id.upper()) == session_id
    with pytest.raises(argparse.ArgumentTypeError):
        session_uuid("not-a-uuid")
    monkeypatch.setattr("sys.argv", ["voice-code", "--dry-run", "--resume", session_id])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
