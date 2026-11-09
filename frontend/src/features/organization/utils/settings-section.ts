export const SETTINGS_SECTIONS = [
  "general",
  "appearance",
  "team",
  "sla",
  "saved-replies",
  "security",
  "notifications",
  "recommendations",
  "widget",
  "shopify",
] as const;

export type SettingsSection = (typeof SETTINGS_SECTIONS)[number];

export function settingsSectionFromHash(hash: string): SettingsSection | null {
  const section = hash.replace(/^#/, "");
  return SETTINGS_SECTIONS.includes(section as SettingsSection)
    ? (section as SettingsSection)
    : null;
}

export function settingsSectionHash(section: SettingsSection): string {
  return `#${section}`;
}
