"""Safe rich-text handling and whitelisted mailbox template expansion."""
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse


ALLOWED_TAGS = {"p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "a"}
VOID_TAGS = {"br"}
BLOCKED_TAGS = {"script", "style", "iframe", "object", "embed", "svg", "math"}
TEMPLATE_VARIABLES = {
    "ten_tts", "email_tts", "ten_chuong_trinh", "ten_mentor",
    "ngay_bat_dau", "ngay_ket_thuc", "ngay_het_han",
}


class _RichTextSanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.blocked_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in BLOCKED_TAGS:
            self.blocked_depth += 1
            return
        if self.blocked_depth or tag not in ALLOWED_TAGS:
            return
        safe_attrs = []
        if tag == "a":
            attributes = {name.lower(): value for name, value in attrs if value is not None}
            href = attributes.get("href", "").strip()
            parsed = urlparse(href)
            if href and parsed.scheme.lower() in {"http", "https", "mailto"}:
                safe_attrs.append(f'href="{escape(href, quote=True)}"')
                safe_attrs.append('rel="noopener noreferrer"')
                safe_attrs.append('target="_blank"')
            title = attributes.get("title", "").strip()
            if title:
                safe_attrs.append(f'title="{escape(title, quote=True)}"')
        suffix = f" {' '.join(safe_attrs)}" if safe_attrs else ""
        self.parts.append(f"<{tag}{suffix}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in BLOCKED_TAGS:
            self.blocked_depth = max(0, self.blocked_depth - 1)
            return
        if not self.blocked_depth and tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.blocked_depth:
            self.parts.append(escape(data))


def sanitize_html(value: str) -> str:
    parser = _RichTextSanitizer()
    parser.feed(value or "")
    parser.close()
    return "".join(parser.parts).strip()


def render_template(value: str, context: dict[str, object]) -> str:
    rendered = value
    for variable in TEMPLATE_VARIABLES:
        rendered = rendered.replace(
            "{" + variable + "}", escape(str(context.get(variable) or "")),
        )
    return rendered
