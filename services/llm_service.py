import logging
import requests
from groq import Groq
from langchain_google_genai import ChatGoogleGenerativeAI
from config import Config

logger = logging.getLogger("loglet_ai")


class LLMService:
    """Handles multi-provider fallback for text generation & transcription."""

    def __init__(self):
        self._groq_client = Groq(api_key=Config.GROQ_API_KEY)

    def _call_openrouter(self, model_name: str, prompt: str) -> str:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {Config.OPENROUTER_API_KEY}",
                "HTTP-Referer": "http://localhost:5000",
                "X-Title": "AI Daily Status Agent",
            },
            json={"model": model_name, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def generate(self, prompt: str) -> tuple[str, str]:
        last_err = None
        for model in Config.GEMINI_CHAIN:
            try:
                llm = ChatGoogleGenerativeAI(model=model, google_api_key=Config.GEMINI_API_KEY, temperature=0.2)
                res = llm.invoke(prompt)
                if res and res.content:
                    if isinstance(res.content, str):
                        text = res.content
                    elif isinstance(res.content, list):
                        parts = []
                        for part in res.content:
                            if isinstance(part, str):
                                parts.append(part)
                            elif isinstance(part, dict) and "text" in part:
                                parts.append(part["text"])
                        text = "".join(parts)
                    else:
                        text = str(res.content)

                    if text and text.strip():
                        return text.strip(), f"Gemini:{model}"
            except Exception as e:
                last_err = e
                logger.warning("Gemini %s failed: %s", model, e)

        for model in Config.GROQ_TEXT_CHAIN:
            try:
                resp = self._groq_client.chat.completions.create(
                    model=model, messages=[{"role": "user", "content": prompt}], temperature=0.2
                )
                content = resp.choices[0].message.content
                if content and content.strip():
                    return content, f"Groq:{model}"
            except Exception as e:
                last_err = e
                logger.warning("Groq %s failed: %s", model, e)

        if Config.OPENROUTER_API_KEY:
            for model in Config.OPENROUTER_CHAIN:
                try:
                    content = self._call_openrouter(model, prompt)
                    if content and content.strip():
                        return content, f"OpenRouter:{model}"
                except Exception as e:
                    last_err = e
                    logger.warning("OpenRouter %s failed: %s", model, e)

        logger.error("All LLM providers failed: %s", last_err)
        raise RuntimeError("generation_failed")

    def transcribe(self, audio_bytes: bytes, prompt_hint: str) -> str:
        last_err = None
        if audio_bytes.startswith(b"\x1a\x45\xdf\xa3"):
            filename = "audio.webm"
        elif audio_bytes.startswith(b"OggS"):
            filename = "audio.ogg"
        elif audio_bytes.startswith(b"ID3") or audio_bytes.startswith(b"\xff\xfb"):
            filename = "audio.mp3"
        else:
            filename = "audio.wav"

        for model in Config.WHISPER_CHAIN:
            try:
                transcript = self._groq_client.audio.transcriptions.create(
                    file=(filename, audio_bytes), model=model, prompt=prompt_hint, response_format="text"
                )
                if transcript and transcript.strip():
                    return transcript
            except Exception as e:
                last_err = e
                logger.warning("Whisper %s failed: %s", model, e)
        logger.error("All transcription models failed: %s", last_err)
        raise RuntimeError("transcription_failed")