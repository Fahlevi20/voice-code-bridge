"""Start a local voice conversation with Claude Code."""

import argparse
import os
from pathlib import Path
import uuid


def session_uuid(value):
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise argparse.ArgumentTypeError("--resume requires a valid session UUID") from exc
    if str(parsed) != value.lower():
        raise argparse.ArgumentTypeError("--resume requires a canonical session UUID")
    return str(parsed)

from .audio import EndpointConfig, LocalTranscriber
from .cli_adapter import ClaudeAdapter
from .controller import VoiceController


def main():
    parser = argparse.ArgumentParser(description="Hands-free voice interface for Claude Code")
    parser.add_argument("--dry-run", action="store_true", help="Transcribe speech without sending it to Claude")
    parser.add_argument("--resume", type=session_uuid, metavar="UUID",
                        help="Continue an explicit, ended Claude Code conversation")
    parser.add_argument("--model", default="base", help="Name of a locally downloaded faster-whisper model")
    parser.add_argument("--model-dir", default=None, help="Directory containing the downloaded speech model")
    parser.add_argument("--language", default=None, help="Speech language, e.g. en; default: autodetect")
    parser.add_argument("--device", type=int, help="Microphone device index")
    parser.add_argument("--threshold", type=float, default=0.016, help="RMS speech threshold")
    parser.add_argument("--silence", type=float, default=1.5, help="Seconds of silence before sending")
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="Working directory for Claude Code")
    args = parser.parse_args()
    if args.resume and args.dry_run:
        parser.error("--resume cannot be used with --dry-run")
    if not args.project.is_dir():
        parser.error("--project must be an existing directory")
    if args.silence <= 0 or args.threshold <= 0:
        parser.error("--silence and --threshold must be positive")
    settings = {k: v for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL", "ANTHROPIC_AUTH_TOKEN")
                if (v := os.environ.get(k))}
    try:
        transcriber = LocalTranscriber(args.model, args.language, args.model_dir)
    except Exception as exc:
        parser.exit(2, f"Local speech model unavailable: {exc}\n"
                          "Download it once with the command in README.md before starting.\n")
    adapter = None if args.dry_run else ClaudeAdapter(
        str(args.project), settings.get("ANTHROPIC_BASE_URL"),
        settings.get("ANTHROPIC_MODEL"), settings.get("ANTHROPIC_AUTH_TOKEN"),
        session_id=args.resume)
    config = EndpointConfig(threshold=args.threshold, silence_seconds=args.silence)
    VoiceController(config, transcriber, adapter, device=args.device, dry_run=args.dry_run).run()


if __name__ == "__main__":
    main()
