# Voice Code (Windows)

A half-duplex voice interface for Claude Code: microphone → **local** faster-whisper transcription → Claude Code CLI → Windows text-to-speech. It submits after roughly 1.5 seconds of silence and reads the full final answer aloud.

## Requirements

- Windows 10/11 with a microphone and speakers; headphones help prevent feedback.
- Python 3.11+ and the [Claude Code CLI](https://code.claude.com/docs/en/setup), installed and authenticated.
- An internet connection for the initial speech-model download and for your configured Claude Code endpoint. **Speech recognition and speech output are local; the transcribed text and conversation context go to the configured model endpoint.**

## Install

From PowerShell in this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
```

Download the `base` speech model once while online (roughly 150 MB):

```powershell
.\.venv\Scripts\python.exe -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
```

After that, speech recognition loads the cached model without downloading again.

## Configure Claude Code

By default the bridge uses the `claude` executable and its existing login/configuration. If you use a compatible custom endpoint, set the relevant variables **in your local shell**, not in tracked files:

```powershell
$env:ANTHROPIC_BASE_URL = 'http://localhost:12345'  # example only
$env:ANTHROPIC_MODEL = 'your-model-id'
# Set ANTHROPIC_AUTH_TOKEN securely in your shell if your endpoint requires it.
```

Do not paste a real token into this repository, its README, screenshots, or GitHub issues. Environment variables are passed to the `claude` child process; the app does not read PowerShell profiles or run shell aliases. Your previous profile alias may still be useful interactively, but this bridge does not invoke it. If an API key is present and an auth token is provided, the child uses the token instead of the key.

## Try it

```powershell
# Check microphone and transcription without contacting Claude Code:
.\.venv\Scripts\python.exe -m voice_code --dry-run

# Start a new voice conversation in the current directory:
.\.venv\Scripts\python.exe -m voice_code
```

Speak a request, pause, and review the printed transcription. When Claude finishes, the full answer prints and plays aloud. Press **Ctrl+C** to stop. Tune `--threshold` (default `0.016`) or `--silence` (default `1.5`) if speech is misdetected. Use `--language en` to constrain recognition; use `--project C:\path\to\your\project` to change the working directory.

### Continue an existing conversation

Obtain the desired CLI session UUID from its session details or configured statusline. **Exit the original Claude Code session first**: running two processes against one session can interleave its transcript. Then run:

```powershell
.\.venv\Scripts\python.exe -m voice_code --resume <session-uuid>
```

Replace the placeholder (including angle brackets) with the real UUID. The bridge never chooses the most recent session automatically or saves the ID to this repository. A restart without `--resume` starts a new conversation. The resumed history carries over, but environment model/endpoint overrides for new voice turns may differ from the original session. If resuming fails, the bridge stops rather than silently starting a new session.

## Safety and limitations

Claude Code runs with `--permission-mode dontAsk --permission-prompts none`: requests requiring approval are denied rather than auto-approved. **This is not a read-only sandbox**: actions already allowed by your Claude Code settings may still run. Choose a working directory you trust, review transcriptions, and use an interactive Claude Code session for consequential changes that need approvals. Background speech or misrecognition can submit a prompt. The microphone is off while Claude works or speaks; voice interruption during playback is not supported. The response is printed and spoken in full, which can reveal private information to nearby people or in terminal recordings.

To list microphone device IDs:

```powershell
.\.venv\Scripts\python.exe -c "import sounddevice; print(sounddevice.query_devices())"
```

Use `--device <index>` if Windows selects the wrong microphone. The model cache can be customized with `--model-dir` (download the model to that directory too). `pyttsx3` uses a local Windows SAPI voice; long answers and code may take a while to read.

## CI and releases

GitHub Actions CI runs the tests and CLI help check on Windows with Python 3.11 and 3.13 for pushes and pull requests to `main`. The release workflow follows the **tag-to-GitHub-Release** pattern in [Quorvin-Web](https://github.com/Quorvin/Quorvin-Web), adapted for Python: a `vMAJOR.MINOR.PATCH` tag triggers tests, verifies that the tag matches `pyproject.toml`'s version, builds a wheel/source distribution, and publishes them as GitHub Release attachments with generated notes. It does **not** deploy anything or publish to PyPI. Releases can also be retried manually with an existing tag. Never create a tag until its commit has passed CI.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests mock the Claude CLI and make no model requests.
