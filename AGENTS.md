# Agent rules - KAZ

These rules are the organization default. Every repository in `kaz-markets` carries a copy.
The canonical text lives here. A copy ships in each repository, because an agent reads the
copy that sits beside the code. Do not edit a copy: change this file, then run
`scripts/sync.mjs`. The `agents guard` check fails a repository whose copy has drifted.

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

## The base app is the product, branding is applied on top

We build one base application and put branding on it, not one app per brand. The base carries
every integration - the routing services, the front-end API packages, the platform - wired and
working, so it is the product. A brand is a name, a logo, colours, copy and a domain applied
to that base at the end. The white label is built in, not bolted on.

- A brand never lives in a code repository. No brand name, logo, colour, copy or domain in
  source; those live in configuration and assets, applied at deploy or runtime.
- A brand never forks the code. Standing up a brand is wiring and configuration, not a branch.
  When a brand seems to need a code change, the base is missing a seam: add the seam to the
  base, so every brand gets it.
- The base and a brand are developed apart, so two developers, two brands, or a brand and the
  base never affect each other.
- Every integration sits behind an interface with a local mock (see Stack), so a new brand or
  a new venue is configuration rather than a rewrite.

This is the lesson from the brands already shipped: the branding belonged on top of a base,
not inside the application.

## Platform constraints

Hard limits, not preferences. If a task cannot be done inside them, stop and say so. Do not
work around them.

### Cloud is free tier only

GCP, and "free tier" means **Always Free SKUs**, not the $300 / 90-day trial credit. The
credit funds any SKU, so leaning on it buys a bill on day 91 and turns billing on for the
project. Treat it as absent.

- No Cloud SQL, no Memorystore, no NAT gateway, no fixed-cost load balancer, no committed
  use, no paid SKU.
- Prefer scale-to-zero (Cloud Run with minimum instances 0) and request-billed storage.
- No always-on VM, with exactly one exception: the Always Free `e2-micro` (one per month, in
  `us-central1`, `us-west1` or `us-east1`, 30GB standard disk, 1GB egress). It exists for the
  one workload that cannot run request-billed, the socket, which holds a long-lived upstream
  connection and needs a stable endpoint. Nothing else belongs on it, and 1GB of egress is a
  real ceiling for a fanout service, so measure before trusting it.
- Anything else paid is the owner's decision, in writing, before any code.

### Data is minimised

- Feed data is transient. Cache it with a TTL and bound the change log. No long-term feed
  history, no archive, no replay store beyond the resume window.
- No real user data. Ever. Not in a fixture, a seed, a test or a database. Demo and
  development run on fake players.
- No real payment data. No card number, no bank details, no processor credentials, no live
  processor. Payments stay a mock behind an adapter.
- Every external capability is an interface with a local mock, and the mock is the default.

### Stack

- Front ends: TypeScript.
- Backends: Python microservices.
- Existing TypeScript services are not rewritten to prove the rule. New backend work is
  Python unless the owner says otherwise for that repository.

### No third party unless asked

Do not add a vendor, SDK, package, SaaS or external API unless the owner asks for it in that
task. No new dependency for something a few lines will do. When an external capability is
genuinely required, define the interface, ship the local mock, and stop.

### Lean, and horizontally scalable

- Services are stateless behind a shared store. No sticky per-process state that breaks when
  a second instance starts.
- Scale out, not up. Nothing assumes exactly one instance except where the code takes a lease
  and says so.
- Bounded memory, bounded queues, bounded logs. Nothing grows without a limit.

### Demo mode: everything is gated

We are in demo. New surfaces ship behind a flag, off by default. No production credentials,
no live providers, no real traffic, no public write path. Seed data is fake. Gating is the
rule, not the exception.

## Running things on GCP

The platform runs on GCP. The free-tier rule and where each piece runs are in
`docs/HOSTING.md`; hostname wiring is in `docs/DOMAINS.md`; the day-to-day commands are in
`docs/RUNNING-ON-GCP.md`. Three things are rules, not advice:

- **No paid SKU without the owner's decision, in writing.** Free tier means Always Free SKUs,
  never the trial credit.
- **Deploy with Workload Identity Federation, never a service-account key.**
- **Captures and galleries are never committed.** Screenshots, QA sweeps and archives live in
  the CDN (Cloudflare R2, `assets.kaz.markets`); git holds code and runtime assets only. See
  `docs/RUNNING-ON-GCP.md` for the upload path.

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

## Report each session

A session ends with a short report to the owner it was run for. An agent working for Jacob
reports to Jacob. An agent working for Dan reports to Dan. This holds for every assistant,
Claude among them.

The report is short and factual: what changed, what is running, what is blocked, and what
needs a decision. Cite the pull request, the issue or the doc instead of restating a diff.

A report is a doc, or a line in `STATUS.md`, not a message. It never mentions a person, and
it never asks for a review, an approval or a merge. The board and the notification rule are
in `docs/TASKS.md`.

## Ground rules

- Fake players only. No real provider, keys or account is contacted from these repos.
- Never commit `.env*`, any `CREDENTIALS.md`, `.data-*` or native build output.
- No em or en dashes, and no bet or wager wording, in player-facing copy.

## The shared checks

- `kaz-markets/.github/.github/workflows/okf.yml` - frontmatter, index parity, doc freshness.
- `kaz-markets/.github/.github/workflows/frontend-guard.yml` - flags a front-end diff.
- `kaz-markets/.github/.github/workflows/agents-guard.yml` - fails when a repository's copy of
  `AGENTS.md` has drifted from the canonical file here.
- `scripts/okf.mjs` in this repository is the one implementation. Each repository carries a
  copy, so `node scripts/okf.mjs --write` works locally. Edit it here, never there.
