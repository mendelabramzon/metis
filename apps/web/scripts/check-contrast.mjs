// Dependency-free WCAG contrast gate for the design tokens (B1).
//
// Parses src/styles/tokens.css, auto-discovers every `--X-bg` / `--X-fg` color pair plus a few
// explicit critical pairs (body text on surfaces, accent foreground on accent), and asserts each
// meets WCAG AA for normal text (4.5:1) in BOTH the light and dark themes. Badge/label text is
// small and bold, so 4.5:1 is the conservative target. Exits non-zero on any failure.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const TOKENS = fileURLToPath(new URL("../src/styles/tokens.css", import.meta.url));
const AA_NORMAL = 4.5;

/** Extract `--name: #hex;` declarations from a CSS block into a {name: hex} map. */
function parseVars(block) {
  const map = {};
  const re = /(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;/g;
  let m;
  while ((m = re.exec(block)) !== null) map[m[1]] = m[2];
  return map;
}

/** The light theme is the first `:root {…}`; the dark theme is the `:root` inside the media query. */
function splitThemes(css) {
  const dark = css.slice(css.indexOf("prefers-color-scheme: dark"));
  const light = css.slice(0, css.indexOf("@media"));
  return { light: parseVars(light), dark: { ...parseVars(light), ...parseVars(dark) } };
}

function toRgb(hex) {
  let h = hex.replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
}

function relativeLuminance(hex) {
  const [r, g, b] = toRgb(hex).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(fg, bg) {
  const a = relativeLuminance(fg);
  const b = relativeLuminance(bg);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

/** Discover {fg, bg} pairs to check, by token name. */
function pairs(vars) {
  const out = [];
  for (const name of Object.keys(vars)) {
    if (name.endsWith("-bg")) {
      const fg = name.replace(/-bg$/, "-fg");
      if (vars[fg]) out.push({ label: name.replace(/^--/, "").replace(/-bg$/, ""), fg, bg: name });
    }
  }
  // Explicit critical pairs the -bg/-fg discovery misses.
  out.push(
    { label: "text/surface", fg: "--color-text", bg: "--color-surface" },
    { label: "text-secondary/surface", fg: "--color-text-secondary", bg: "--color-surface" },
    { label: "text-muted/surface", fg: "--color-text-muted", bg: "--color-surface" },
    { label: "text/canvas", fg: "--color-text", bg: "--color-canvas" },
    { label: "text-muted/canvas", fg: "--color-text-muted", bg: "--color-canvas" },
    { label: "accent-fg/accent", fg: "--color-accent-fg", bg: "--color-accent" },
  );
  return out;
}

const css = readFileSync(TOKENS, "utf8");
const themes = splitThemes(css);
let failures = 0;

for (const [theme, vars] of Object.entries(themes)) {
  for (const { label, fg, bg } of pairs(vars)) {
    const fgHex = vars[fg];
    const bgHex = vars[bg];
    if (!fgHex || !bgHex) {
      console.error(`  MISSING  ${theme.padEnd(5)} ${label} (${fg} on ${bg})`);
      failures++;
      continue;
    }
    const ratio = contrast(fgHex, bgHex);
    if (ratio < AA_NORMAL) {
      console.error(`  FAIL     ${theme.padEnd(5)} ${label}: ${ratio.toFixed(2)}:1 (< ${AA_NORMAL})`);
      failures++;
    }
  }
}

if (failures > 0) {
  console.error(`\ncontrast check: ${failures} pair(s) below WCAG AA (${AA_NORMAL}:1)`);
  process.exit(1);
}
console.log("contrast check: all token pairs meet WCAG AA (4.5:1) in light and dark");
