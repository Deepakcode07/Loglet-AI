import io
import logging
import numpy as np
import soundfile as sf
import noisereduce as nr

logger = logging.getLogger("loglet_ai")


class AudioProcessor:
    """Denoises raw mic audio before it hits the transcription model."""

    def clean(self, audio_bytes: bytes) -> bytes:
        try:
            data, samplerate = sf.read(io.BytesIO(audio_bytes), dtype="float32")
            if data.ndim > 1:
                data = data.mean(axis=1)  # downmix to mono

            # Spectral-gating noise reduction (free, no native deps)
            reduced = nr.reduce_noise(y=data, sr=samplerate, stationary=False, prop_decrease=0.75)

            # Normalize to avoid clipping/silence issues after reduction
            peak = np.max(np.abs(reduced)) or 1.0
            reduced = reduced / peak * 0.95

            out = io.BytesIO()
            sf.write(out, reduced, samplerate, format="WAV")
            return out.getvalue()
        except Exception as e:
            logger.warning("Noise reduction skipped, using raw audio: %s", e)
            return audio_bytes  # fail-safe: never block transcription

    
    def speech_ratio(self, audio_bytes: bytes) -> float:
        """Returns fraction of audio (0-1) classified as speech via WebRTC VAD.
        Cheap, fast, catches: silence, pure music/noise, empty recordings."""
        try:
            import webrtcvad
            vad = webrtcvad.Vad(2)  # aggressiveness 0-3; 2 = balanced
            data, sr = sf.read(io.BytesIO(audio_bytes), dtype="int16")
            if data.ndim > 1:
                data = data.mean(axis=1).astype("int16")
            if sr not in (8000, 16000, 32000, 48000):
                return 1.0  # unsupported rate, skip gate rather than false-reject

            frame_ms = 30
            frame_len = int(sr * frame_ms / 1000)
            frames = [data[i:i+frame_len].tobytes() for i in range(0, len(data) - frame_len, frame_len)]
            if not frames:
                return 0.0

            speech_frames = sum(1 for f in frames if len(f) == frame_len * 2 and vad.is_speech(f, sr))
            return speech_frames / len(frames)
        except Exception as e:
            logger.warning("speech_ratio skipped: %s", e)
            return 1.0  # fail-safe: never block valid audio