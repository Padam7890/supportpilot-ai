MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS_PER_CONVERSATION = 20
MAX_CONVERSATION_ATTACHMENT_BYTES = 100 * 1024 * 1024

ALLOWED_ATTACHMENT_TYPES = {
    ".png": ("image/png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
    ".webp": ("image/webp", lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"),
    ".pdf": ("application/pdf", lambda data: data.startswith(b"%PDF-")),
    ".txt": ("text/plain", lambda data: _is_utf8_text(data)),
    ".md": ("text/markdown", lambda data: _is_utf8_text(data)),
}


def _is_utf8_text(data: bytes) -> bool:
    try:
        return b"\x00" not in data and data.decode("utf-8") is not None
    except UnicodeDecodeError:
        return False
