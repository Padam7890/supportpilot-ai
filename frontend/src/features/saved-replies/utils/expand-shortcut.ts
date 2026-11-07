export interface SavedReplyShortcut {
  shortcut: string;
  body: string;
}

export interface ShortcutExpansion {
  value: string;
  cursor: number;
  shortcut: string;
}

export function expandSavedReplyAtCursor(
  value: string,
  cursor: number,
  replies: readonly SavedReplyShortcut[],
): ShortcutExpansion | null {
  const prefix = value.slice(0, cursor);
  const match = /(?:^|\s)\/([a-z0-9][a-z0-9_-]{1,39})$/i.exec(prefix);
  if (!match) return null;

  const shortcut = match[1].toLowerCase();
  const reply = replies.find((item) => item.shortcut.toLowerCase() === shortcut);
  if (!reply) return null;

  const tokenStart = cursor - shortcut.length - 1;
  const suffix = value.slice(cursor);
  const separator = suffix && !/^\s/.test(suffix) && !/\s$/.test(reply.body) ? " " : "";
  const insertion = `${reply.body}${separator}`;

  return {
    value: `${value.slice(0, tokenStart)}${insertion}${suffix}`,
    cursor: tokenStart + insertion.length,
    shortcut,
  };
}
