#!/usr/bin/env node
// OKF: check and generate a knowledge bundle.
//
//   node scripts/okf.mjs --check
//   node scripts/okf.mjs --check --base origin/main
//   node scripts/okf.mjs --write
//
// Validates every doc under the bundle: frontmatter present and well formed, and
// the generated block of the index in parity with the files on disk. With
// --base <ref>, also fails when a diff touches code a doc covers and that doc is
// not in the same diff.
//
// No dependencies. Node 20+.

import { readdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { join, relative, sep, posix } from "node:path";
import { execFileSync } from "node:child_process";

const argv = process.argv.slice(2);
const has = (name) => argv.includes(name);
const value = (name, fallback) => {
  const i = argv.indexOf(name);
  return i === -1 ? fallback : argv[i + 1];
};

const root = value("--root", ".");
const bundle = value("--bundle", "docs");
const indexRel = value("--index", posix.join(bundle, "INDEX.md"));
const write = has("--write");
const base = value("--base", "");

const TYPES = new Set(["design", "runbook", "plan", "reference"]);
const OWNERS = new Set(["dan", "jacob"]);
const REQUIRED = ["type", "title", "description", "owner", "tags", "timestamp", "code"];
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$/;
const START = "<!-- okf:index:start -->";
const END = "<!-- okf:index:end -->";

const errors = [];
const warnings = [];
const fail = (msg) => errors.push(msg);
const warn = (msg) => warnings.push(msg);

// ---------------------------------------------------------------- discovery

function walk(dir, out = []) {
  if (!existsSync(dir)) return out;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === ".git" || entry.name === "node_modules") continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else if (entry.name.endsWith(".md")) out.push(full);
  }
  return out;
}

function unquote(raw) {
  const t = raw.trim();
  if ((t.startsWith('"') && t.endsWith('"')) || (t.startsWith("'") && t.endsWith("'"))) {
    return t.slice(1, -1);
  }
  return t;
}

function parseValue(raw) {
  const t = raw.trim();
  if (t.startsWith("[") && t.endsWith("]")) {
    return t
      .slice(1, -1)
      .split(",")
      .map((p) => unquote(p))
      .filter((p) => p.length > 0);
  }
  return unquote(t);
}

function parseDoc(file) {
  const text = readFileSync(file, "utf8");
  if (!text.startsWith("---\n") && !text.startsWith("---\r\n")) {
    return { error: "no frontmatter block" };
  }
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n/.exec(text);
  if (!match) return { error: "frontmatter block is not closed" };

  const data = {};
  for (const line of match[1].split(/\r?\n/)) {
    if (!line.trim() || line.trim().startsWith("#")) continue;
    const colon = line.indexOf(":");
    if (colon === -1) {
      return { error: `frontmatter line is not key: value: ${line.trim()}` };
    }
    data[line.slice(0, colon).trim()] = parseValue(line.slice(colon + 1));
  }
  return { data, body: text.slice(match[0].length) };
}

// ------------------------------------------------------------------- checks

const bundlePath = join(root, bundle);
const indexPath = join(root, indexRel);
const files = walk(bundlePath).sort();
const docs = files.filter((f) => relative(root, f) !== indexRel);

if (files.length === 0) {
  warn(`no bundle at ${bundle}/ yet; nothing to check`);
}

const indexText = existsSync(indexPath) ? readFileSync(indexPath, "utf8") : null;
if (indexText === null) fail(`no index at ${indexRel}`);

const rows = [];
for (const file of docs) {
  const rel = relative(root, file).split(sep).join("/");
  const parsed = parseDoc(file);
  if (parsed.error) {
    fail(`${rel}: ${parsed.error}`);
    continue;
  }
  const d = parsed.data;
  for (const key of REQUIRED) {
    if (!(key in d)) fail(`${rel}: frontmatter is missing \`${key}\``);
  }
  if (d.type && !TYPES.has(d.type)) {
    fail(`${rel}: type \`${d.type}\` is not one of ${[...TYPES].join(", ")}`);
  }
  if (d.owner && !OWNERS.has(d.owner)) {
    fail(`${rel}: owner \`${d.owner}\` is not one of ${[...OWNERS].join(", ")}`);
  }
  if (d.timestamp && !ISO.test(d.timestamp)) {
    fail(`${rel}: timestamp \`${d.timestamp}\` is not ISO 8601`);
  }
  for (const key of ["tags", "code"]) {
    if (key in d && !Array.isArray(d[key])) fail(`${rel}: \`${key}\` must be a list`);
  }
  for (const key of ["title", "description"]) {
    if (key in d && String(d[key]).trim().length === 0) fail(`${rel}: \`${key}\` is empty`);
  }
  rows.push({ rel, data: d });
}

// ------------------------------------------------------------- index parity

const indexDir = posix.dirname(indexRel);

function parityProblems(text) {
  const found = [];
  const linked = new Set();
  const re = /\]\(([^)]+)\)/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const target = m[1].split("#")[0].trim();
    if (!target || /^[a-z]+:/i.test(target) || target.startsWith("/")) continue;
    const resolved = posix.normalize(posix.join(indexDir, target));
    if (resolved.startsWith("..")) continue;
    linked.add(resolved);
    if (resolved.endsWith(".md") && !existsSync(join(root, resolved))) {
      found.push(`${indexRel}: link to ${target} does not exist`);
    }
  }
  for (const { rel } of rows) {
    if (!linked.has(rel)) found.push(`${indexRel}: no row for ${rel}`);
  }
  return found;
}

if (indexText !== null && !write) {
  for (const problem of parityProblems(indexText)) fail(problem);
}

// --------------------------------------------------------- doc freshness

function globToRegExp(glob) {
  const escaped = glob.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  const body = escaped
    .replace(/\*\*\//g, "(?:.*/)?")
    .replace(/\*\*/g, ".*")
    .replace(/\*/g, "[^/]*")
    .replace(/\?/g, "[^/]");
  return new RegExp(`^${body}$`);
}

function changedSince(ref) {
  try {
    const out = execFileSync("git", ["diff", "--name-only", `${ref}...HEAD`], {
      cwd: root,
      encoding: "utf8",
    });
    return out.split("\n").map((l) => l.trim()).filter(Boolean);
  } catch (e) {
    warn(`could not diff against ${ref}: ${String(e.message).split("\n")[0]}`);
    return null;
  }
}

if (base) {
  const changed = changedSince(base);
  if (changed !== null) {
    const changedSet = new Set(changed);
    for (const { rel, data } of rows) {
      const globs = Array.isArray(data.code) ? data.code : [];
      const hit = changed.find((path) =>
        globs.some((glob) => globToRegExp(glob).test(path))
      );
      if (hit && !changedSet.has(rel)) {
        fail(
          `${rel}: ${hit} changed in this diff, so this doc is in scope. ` +
            `Update it in the same PR.`
        );
      }
    }
  }
}

// ------------------------------------------------------------------ output

function table() {
  const lines = [
    "| Doc | Covers | Owner | Code |",
    "| --- | --- | --- | --- |",
  ];
  for (const { rel, data } of rows) {
    const target = posix.relative(indexDir, rel) || rel;
    const code = (Array.isArray(data.code) ? data.code : [])
      .map((c) => `\`${c}\``)
      .join(", ");
    lines.push(
      `| [${target}](${target}) | ${data.description ?? ""} | ${data.owner ?? ""} | ${code} |`
    );
  }
  return lines.join("\n");
}

function regenerate() {
  if (indexText === null) {
    fail(`--write needs an index at ${indexRel}`);
    return;
  }
  const start = indexText.indexOf(START);
  const end = indexText.indexOf(END);
  if (start === -1 || end === -1 || end < start) {
    fail(`${indexRel}: add ${START} and ${END} around the table, then run --write`);
    return;
  }
  const next =
    indexText.slice(0, start + START.length) +
    "\n\n" +
    table() +
    "\n\n" +
    indexText.slice(end);
  if (next !== indexText) {
    writeFileSync(indexPath, next);
    console.log(`okf: rewrote the table in ${indexRel}`);
  } else {
    console.log(`okf: ${indexRel} already current`);
  }
}

if (write && errors.length === 0) {
  regenerate();
  if (existsSync(indexPath)) {
    for (const problem of parityProblems(readFileSync(indexPath, "utf8"))) fail(problem);
  }
}

for (const w of warnings) console.log(`okf: note: ${w}`);
for (const e of errors) console.error(`okf: error: ${e}`);

if (errors.length > 0) {
  console.error(`okf: ${errors.length} problem(s)`);
  process.exit(1);
}

console.log(`okf: ${rows.length} doc(s) in ${bundle}/ are in order`);
