import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

    GEMINI_CHAIN = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-flash-latest"]
    GROQ_TEXT_CHAIN = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"]
    WHISPER_CHAIN = ["whisper-large-v3", "whisper-large-v3-turbo"]
    OPENROUTER_CHAIN = [
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "openai/gpt-oss-120b:free",
        "google/gemma-2-27b-it:free",
        "openrouter/free",
    ]

    MAX_INPUT_CHARS = 6000
    MAX_CONTEXT_CHARS = 800
    MAX_PREFIX_CHARS = 12

    @staticmethod
    def validate():
        if not Config.GROQ_API_KEY or not Config.GEMINI_API_KEY:
            raise RuntimeError("Missing GROQ_API_KEY or GEMINI_API_KEY")