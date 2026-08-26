import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const styles = path.join(root, "src", "styles");
const entry = path.join(styles, "app.css");

function fail(message) {
  console.error(`CSS contract failed: ${message}`);
  process.exitCode = 1;
}

const expected = [
  "./react-base.css",
  "./separated.css",
  "./lifeos/public.css",
  "./lifeos/style.css",
  "./lifeos/theme-v2.css",
  "./lifeos/project-studio.css",
  "./lifeos/focus.css",
  "./react-native-extras.css",
  "./visual-parity.css",
  "./layout-foundation.css",
  "./lifeos/polish.css",
  "./ux-refresh.css",
  "./document-brain.css",
];

const source = fs.readFileSync(entry, "utf8");
const imports = [...source.matchAll(/@import\s+["']([^"']+)["'];/g)].map((m) => m[1]);
if (JSON.stringify(imports) !== JSON.stringify(expected)) {
  fail(`app.css import order changed.\nExpected: ${expected.join(" -> ")}\nActual:   ${imports.join(" -> ")}`);
}
if (source.includes("global.css")) fail("obsolete global.css must not be imported.");

const main = fs.readFileSync(path.join(root, "src", "main.tsx"), "utf8");
const styleImports = [...main.matchAll(/import\s+["']\.\/styles\/([^"']+\.css)["'];/g)].map((m) => m[1]);
if (styleImports.length !== 1 || styleImports[0] !== "app.css") {
  fail(`src/main.tsx must import only styles/app.css; found ${styleImports.join(", ") || "none"}.`);
}

// A second .app-shell grid was the root cause of the site-wide collapse.  Guard
// against reintroducing that structural contract in any actively imported file.
for (const relative of imports) {
  const full = path.resolve(styles, relative);
  const css = fs.readFileSync(full, "utf8");
  const shellBlocks = [...css.matchAll(/([^{}]*\.app-shell[^{}]*)\{([^}]*)\}/g)];
  for (const [, selector, body] of shellBlocks) {
    const normalized = body.replace(/\s+/g, " ").toLowerCase();
    if (normalized.includes("grid-template-columns") || /display\s*:\s*grid/.test(normalized)) {
      fail(`${relative} defines a CSS-grid .app-shell (${selector.trim()}). The canonical shell is fixed-sidebar + main canvas.`);
    }
  }
}

const layout = fs.readFileSync(path.join(styles, "layout-foundation.css"), "utf8");
for (const required of [
  ".app-shell",
  "display: block !important",
  ".app-main",
  "margin-left: 280px !important",
  ".dashboard-main-grid",
  ".db-document-grid",
]) {
  if (!layout.includes(required)) fail(`layout-foundation.css is missing required contract token: ${required}`);
}

if (!process.exitCode) {
  console.log("CSS contract OK: one entrypoint, deterministic cascade, canonical shell protected.");
}
