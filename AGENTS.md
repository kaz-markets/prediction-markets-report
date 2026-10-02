# Agent rules - KAZ

These rules are the organization default. Every repository in `kaz-markets` carries a copy.
The canonical text lives here; `sync` writes the copies.

## The knowledge bundle comes first

A repository's `docs/` folder is its OKF (Open Knowledge Format) bundle: one Markdown file
per concept, YAML frontmatter on top, everything in Git. It is the authoritative answer for
how that repository works. Chat, tickets and memory are not.

Before you answer a question about the platform, or change anything:

1. Read `docs/INDEX.md`. It is one page: every doc, what it covers, whose it is.
2. Open the one doc that matches. Do not answer from memory.
3. If no doc matches, say so, then write it as part of the change.

## The doc is part of the change

A code change that alters behaviour is not done until the matching doc under `docs/` says the
new thing. Same PR, same commit. The `code` field in a doc's frontmatter lists the paths that
doc covers; if your diff touches one of them, that doc is in scope. The `okf` workflow checks
this and fails the PR when it is skipped.

## Front end is out of bounds

`app/`, `admin/`, `mobile/`, `site/` and `bet105-concept/` are the front end. Do not edit
them unless the owner asks for it in that task. Platform, backend, service and `docs/` work
is the work. When a front-end change looks required, stop and say so instead of making it.

## Frontmatter

Every file in `docs/` starts with these fields. Keep them true.

```yaml
---
type: design
title: "Trading"
description: "Odds feed, pricing, watchdog and book controls."
owner: dan
tags: [trading, odds, pricing]
timestamp: 2026-10-01T14:05:00Z
code: ["server/src/trading/**"]
---
```

- `type`: `design`, `runbook`, `plan` or `reference`.
- `owner`: the person who keeps it true.
- `timestamp`: when the doc last changed. Do not bump it without changing the doc.
- `code`: the paths this doc describes. `[]` when the doc is a plan with no code yet.

The generated part of `docs/INDEX.md` lives between `<!-- okf:index:start -->` and
`<!-- okf:index:end -->`. Never hand-edit that block; run `okf:write`.

## Is a doc stale?

Compare when the doc last changed with when the code it covers last changed. Code newer than
the doc means the doc is stale.

```bash
git log -1 --format=%cs -- docs/TRADING.md
git log -1 --format=%cs -- 'server/src/trading'
```

## STATUS.md is the only volatile doc

Where a repository has a `STATUS.md`, it is rewritten every session: what is running, what is
paused, what the owner decided. Never append to it, and never let it go a day without an edit.
Everything else in `docs/` is stable and edited in place.

## Ground rules

- Fake players only. No real provider, keys or account is contacted from these repos.
- Never commit `.env*`, any `CREDENTIALS.md`, `.data-*` or native build output.
- No em or en dashes, and no bet or wager wording, in player-facing copy.

## The shared checks

- `kaz-markets/.github/.github/workflows/okf.yml` - frontmatter, index parity, doc freshness.
- `kaz-markets/.github/.github/workflows/frontend-guard.yml` - flags a front-end diff.
- `scripts/okf.mjs` in this repository is the one implementation. `sync` writes a copy into
  each repository so `node scripts/okf.mjs --write` works locally. Edit it here, never there.
