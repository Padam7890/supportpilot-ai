const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;
const ALLOWED_EXTENSIONS = new Set(["png", "jpg", "jpeg", "webp", "pdf", "txt", "md"]);

export function getAttachmentValidationError(file: File): string | null {
  if (file.size === 0) return "Choose a non-empty file.";
  if (file.size > MAX_ATTACHMENT_BYTES) return "Each team file must be 10 MB or smaller.";

  const extension = file.name.split(".").pop()?.toLowerCase();
  if (!extension || !ALLOWED_EXTENSIONS.has(extension)) {
    return "Choose a PNG, JPEG, WebP, PDF, TXT, or Markdown file.";
  }

  return null;
}
