import re
import html


class RichTextFormatter:
    """Converts markdown report -> styled HTML fragment.
    Browser clipboard then copies it as real bold/headings (Word/Slack/Docs paste
    correctly formatted, no stray # or ** characters)."""

    @staticmethod
    def to_html(markdown_text: str) -> str:
        text = html.escape(markdown_text)
        # Headers
        text = re.sub(r'^## (.+)$', r'<h3 style="margin:14px 0 6px;font-weight:700;">\1</h3>', text, flags=re.M)
        text = re.sub(r'^# (.+)$', r'<h2 style="margin:16px 0 8px;font-weight:800;">\1</h2>', text, flags=re.M)
        # Bold
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        # Bullets
        lines = text.split("\n")
        out, in_list = [], False
        for line in lines:
            if line.strip().startswith("- "):
                if not in_list:
                    out.append("<ul style='margin:4px 0;padding-left:20px;'>")
                    in_list = True
                out.append(f"<li>{line.strip()[2:]}</li>")
            else:
                if in_list:
                    out.append("</ul>")
                    in_list = False
                if line.strip():
                    if line.startswith("<h2") or line.startswith("<h3"):
                        out.append(line)
                    else:
                        out.append(f"<p style='margin:4px 0;'>{line}</p>")
        if in_list:
            out.append("</ul>")
        return "".join(out)