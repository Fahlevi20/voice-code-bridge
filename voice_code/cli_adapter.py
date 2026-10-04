"""Safe, noninteractive Claude Code CLI adapter."""

import json
import os
import shutil
import subprocess


class CliError(RuntimeError):
    pass


class ResumeError(CliError):
    pass


class ClaudeAdapter:
    def __init__(self, cwd, base_url=None, model=None, auth_token=None, executable=None,
                 runner=None, session_id=None):
        self.cwd = cwd
        self.base_url = base_url
        self.model = model
        self.auth_token = auth_token
        self.executable = executable or shutil.which("claude")
        if not self.executable:
            raise CliError("Claude Code CLI not found on PATH")
        self.runner = runner or subprocess.run
        self.session_id = session_id

    def ask(self, prompt):
        args = [self.executable, "-p", prompt, "--output-format", "json",
                "--permission-mode", "dontAsk", "--permission-prompts", "none"]
        if self.session_id:
            args.extend(["--resume", self.session_id])
        env = os.environ.copy()
        if self.base_url:
            env["ANTHROPIC_BASE_URL"] = self.base_url
        if self.model:
            env["ANTHROPIC_MODEL"] = self.model
        if self.auth_token:
            env.pop("ANTHROPIC_API_KEY", None)
            env["ANTHROPIC_AUTH_TOKEN"] = self.auth_token
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            completed = self.runner(args, cwd=self.cwd, env=env, input="", text=True,
                                    encoding="utf-8", errors="replace", capture_output=True)
        except OSError as exc:
            raise CliError(f"Could not launch Claude Code: {exc}") from exc
        try:
            result = json.loads(completed.stdout)
        except (ValueError, TypeError) as exc:
            if self.session_id:
                raise ResumeError(f"Could not resume session {self.session_id}; Claude Code returned no JSON. "
                                  "Check that the session has ended and is available locally.") from exc
            raise CliError("Claude Code did not return JSON; check that the CLI and proxy are available") from exc
        if not isinstance(result, dict):
            raise CliError("Claude Code returned an unexpected result")
        text = result.get("result")
        if completed.returncode != 0 or result.get("is_error"):
            if self.session_id:
                raise ResumeError(f"Could not continue session {self.session_id}: "
                                  f"{text or 'Claude Code request failed'}")
            raise CliError(str(text or "Claude Code request failed"))
        returned_id = result.get("session_id")
        if self.session_id and returned_id != self.session_id:
            raise ResumeError(f"Claude Code returned a different session ID while resuming "
                              f"{self.session_id}; stopping rather than switching conversations.")
        if not isinstance(returned_id, str) or not returned_id:
            raise CliError("Claude Code returned no session ID")
        if not isinstance(text, str):
            raise CliError("Claude Code returned no final answer")
        self.session_id = returned_id
        denied = result.get("permission_denials") or []
        if denied:
            text += ("\n\nSome tool actions were denied because this unattended voice session "
                     "does not approve them. Review those actions in an interactive Claude Code session.")
        return text
