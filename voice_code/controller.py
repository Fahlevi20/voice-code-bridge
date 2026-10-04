"""Half-duplex voice conversation controller."""

import time

from .audio import listen, speak
from .cli_adapter import ResumeError


class VoiceController:
    def __init__(self, config, transcriber, adapter, device=None, dry_run=False,
                 listener=listen, speaker=speak):
        self.config = config
        self.transcriber = transcriber
        self.adapter = adapter
        self.device = device
        self.dry_run = dry_run
        self.listener = listener
        self.speaker = speaker

    def once(self):
        print("Listening... (Ctrl+C to stop)", flush=True)
        audio = self.listener(self.config, self.device)
        text = self.transcriber.transcribe(audio).strip()
        if not text:
            print("No speech recognized; listening again.", flush=True)
            return
        print(f"You: {text}", flush=True)
        if self.dry_run:
            return
        print("Working...", flush=True)
        answer = self.adapter.ask(text)
        print(f"\nAssistant:\n{answer}\n", flush=True)
        if answer.strip():
            self.speaker(answer)
            time.sleep(0.3)

    def run(self):
        while True:
            try:
                self.once()
            except KeyboardInterrupt:
                print("\nStopped.", flush=True)
                return
            except ResumeError as exc:
                print(f"Session handoff stopped: {exc}", flush=True)
                return
            except Exception as exc:
                # Keep the loop usable after a failed transcription or CLI request.
                print(f"Error: {exc}", flush=True)
                time.sleep(1)
