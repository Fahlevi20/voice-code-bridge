"""Microphone endpointing and local speech input/output."""

from collections import deque
from dataclasses import dataclass
import queue
import threading

import numpy as np


@dataclass
class EndpointConfig:
    sample_rate: int = 16000
    block_seconds: float = 0.05
    threshold: float = 0.016
    silence_seconds: float = 1.5
    min_speech_seconds: float = 0.2
    max_seconds: float = 45.0
    preroll_seconds: float = 0.3


class SpeechEndpoint:
    def __init__(self, config: EndpointConfig):
        self.config = config
        self.preroll = deque(maxlen=max(1, round(config.preroll_seconds / config.block_seconds)))
        self.reset()

    def reset(self):
        self.frames = []
        self.speaking = False
        self.speech_blocks = 0
        self.silence_blocks = 0
        self.recorded_samples = 0
        self.preroll.clear()

    def feed(self, frame):
        """Return a completed utterance, or None if recording continues."""
        frame = np.asarray(frame, dtype=np.float32).reshape(-1).copy()
        rms = float(np.sqrt(np.mean(frame * frame))) if frame.size else 0.0
        voiced = rms >= self.config.threshold
        if not self.speaking:
            self.preroll.append(frame)
            if not voiced:
                return None
            self.speaking = True
            self.frames.extend(self.preroll)
            self.recorded_samples = sum(len(chunk) for chunk in self.frames)
            self.preroll.clear()
            self.speech_blocks = 1
            return None

        self.frames.append(frame)
        self.recorded_samples += len(frame)
        if voiced:
            self.speech_blocks += 1
            self.silence_blocks = 0
        else:
            self.silence_blocks += 1

        elapsed = self.recorded_samples / self.config.sample_rate
        finished = (self.silence_blocks * self.config.block_seconds >= self.config.silence_seconds
                    or elapsed >= self.config.max_seconds)
        if not finished:
            return None
        enough_speech = self.speech_blocks * self.config.block_seconds >= self.config.min_speech_seconds
        audio = np.concatenate(self.frames) if enough_speech else None
        self.reset()
        return audio


def listen(config: EndpointConfig, device=None):
    """Capture one utterance; stop streaming before returning to avoid TTS echo."""
    import sounddevice as sd

    endpoint = SpeechEndpoint(config)
    frames = queue.Queue(maxsize=64)
    overflow = threading.Event()
    blocksize = round(config.sample_rate * config.block_seconds)

    def callback(indata, frame_count, time_info, status):
        if status:
            overflow.set()
        try:
            frames.put_nowait(indata[:, 0].copy())
        except queue.Full:
            overflow.set()

    with sd.InputStream(samplerate=config.sample_rate, channels=1, dtype="float32",
                        blocksize=blocksize, device=device, callback=callback):
        while True:
            if overflow.is_set():
                raise RuntimeError("Microphone input overran; select a working input device or reduce load")
            audio = endpoint.feed(frames.get(timeout=1))
            if audio is not None:
                return audio


class LocalTranscriber:
    def __init__(self, model_name="base", language=None, model_dir=None):
        from faster_whisper import WhisperModel

        self.model = WhisperModel(model_name, device="cpu", compute_type="int8",
                                  download_root=model_dir, local_files_only=True)
        self.language = language

    def transcribe(self, audio):
        segments, _ = self.model.transcribe(audio, language=self.language,
                                            vad_filter=True, beam_size=5)
        return " ".join(segment.text.strip() for segment in segments).strip()


def speak(text):
    import pyttsx3

    engine = pyttsx3.init()
    try:
        engine.say(text)
        engine.runAndWait()
    finally:
        engine.stop()
