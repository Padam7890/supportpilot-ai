export const TYPOGRAPHY_SCALES = ["compact", "balanced", "comfortable"] as const;

export type TypographyScale = (typeof TYPOGRAPHY_SCALES)[number];

export const TYPOGRAPHY_SCALE_STORAGE_KEY = "supportpilot-typography-scale";

export const TYPOGRAPHY_SCALE_CHANGE_EVENT = "supportpilot-typography-scale-change";

export function isTypographyScale(value: string | null | undefined): value is TypographyScale {
  return value != null && (TYPOGRAPHY_SCALES as readonly string[]).includes(value);
}

export function readTypographyScale(): TypographyScale {
  if (typeof window === "undefined") return "balanced";
  const saved = window.localStorage.getItem(TYPOGRAPHY_SCALE_STORAGE_KEY);
  return isTypographyScale(saved) ? saved : "balanced";
}

export function applyTypographyScale(scale: TypographyScale) {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.typographyScale = scale;
}

export function setTypographyScale(scale: TypographyScale) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TYPOGRAPHY_SCALE_STORAGE_KEY, scale);
  applyTypographyScale(scale);
  window.dispatchEvent(new Event(TYPOGRAPHY_SCALE_CHANGE_EVENT));
}

export function ensureTypographyScaleFromStorage() {
  applyTypographyScale(readTypographyScale());
}
