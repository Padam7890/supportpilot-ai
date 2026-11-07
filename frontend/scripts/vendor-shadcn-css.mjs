import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outDir = path.join(root, "src/app/styles");

const sources = [
  ["node_modules/tw-animate-css/dist/tw-animate.css", "tw-animate.css"],
  ["node_modules/shadcn/dist/tailwind.css", "shadcn-tailwind.css"],
];

mkdirSync(outDir, { recursive: true });

let copied = 0;
for (const [fromRel, toName] of sources) {
  const from = path.join(root, fromRel);
  if (!existsSync(from)) continue;
  copyFileSync(from, path.join(outDir, toName));
  copied += 1;
}

if (copied < sources.length) {
  console.warn(
    `[vendor-shadcn-css] Skipped ${sources.length - copied} file(s); committed copies in src/app/styles are used.`,
  );
}
