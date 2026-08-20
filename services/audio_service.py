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