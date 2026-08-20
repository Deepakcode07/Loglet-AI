class Sanitizer:
    @staticmethod
    def text(value: str, max_chars: int) -> str:
        if not value:
            return ""
        value = value.strip()[:max_chars]
        for tag in ("</USER_UPDATE>", "<USER_UPDATE>", "</STYLE_NOTE>", "<STYLE_NOTE>"):
            value = value.replace(tag, "")
        return value

    @staticmethod
    def prefix(value: str, max_chars: int) -> str:
        cleaned = "".join(c for c in (value or "") if c.isalnum() or c in "-_")[:max_chars]
        return cleaned or "DEV-"