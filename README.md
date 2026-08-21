# Utah License Prep

A single-file study suite for the Utah electrical and contractor licensing exams, served as a
static page from this repo.

**Live:** [mason-page.github.io/utah-license-prep](https://mason-page.github.io/utah-license-prep)  
*(URL updated 2026-08-20 ahead of the `longevexcoaching` → `mason-page` account rename — see `brain/_shared/ACCOUNT-RENAME-RUNBOOK.md`. Until that rename is clicked, the old `longevexcoaching.github.io` address is the one that works.)*

> **This repo is PUBLIC.** It serves the app via GitHub Pages, so everything committed here is
> world-readable. Nothing sensitive goes in — no keys, no client material, no exam material that
> isn't yours to publish. The Snap & Solve tool's Gemini key is entered by the user at runtime and
> lives in the browser's `localStorage` only; it must never appear anywhere in this file tree.

## What's in here

| File | |
|---|---|
| `index.html` | The whole app — five sub-apps embedded as base64 blobs, ~315 KB |
| `check-bank.py` | Regression guard for the question banks (see below) |
| `bank-baseline.json` | The committed baseline `check-bank.py` compares against |

Five tools, one menu, one file. Install to a phone home screen via **Share → Add to Home Screen**;
it runs full-screen and offline-friendly.

| Sub-app | What it drills |
|---|---|
| `theory` | Theory From Zero — electrical theory from scratch |
| `resj` | Residential Journeyman — written exam + Calc Gym |
| `nec` | Utah NEC Code — 2023 NEC plus Utah's 20 statewide amendments |
| `b100` | B100 Contractor — General Building Business & Law |
| `snap` | Snap & Solve — photograph a question, get the answer and the reasoning |

Current bank: **256 questions** across the three question-bank sub-apps (`b100` 82, `nec` 55,
`resj` 119). `theory` and `snap` carry no bank by design.

## Before you commit a change to `index.html`

```
python check-bank.py            # verify against the baseline — exit 1 on regression
python check-bank.py --verbose  # per-domain question counts
python check-bank.py --update   # re-baseline, ONLY after reviewing the change
```

This is not optional ceremony. The sub-apps are base64 blobs, which makes the git diff unreadable
by design — **PR #1 silently deleted the entire Snap & Solve sub-app and nothing caught it** except
a human decoding the payload by hand. `check-bank.py` decodes every sub-app, checks it isn't
truncated, parses the question banks, and fails loudly on: a deleted sub-app, dropped questions, a
vanished domain, a domain missing from `WEIGHTS` (its questions would never be drawn), an
out-of-range answer index, duplicate question text, or a missing explanation/code reference.

Question growth shows as a **warning**, not a failure — review the new questions, then `--update`.

When writing new questions, spread the correct answer evenly across the option positions; don't let
it cluster on one letter.

## Browser tests — the `snap-tests` sibling

`check-bank.py` proves each sub-app decodes and is intact, but Snap & Solve has no question bank, so
every content assertion in the checker is vacuous for it. A Playwright suite covers the rest — what
the app does, what it sends on the wire, and what it claims about Utah law:

**[`../personal-brand/projects/utah-license-prep-snap-tests/`](../personal-brand/projects/utah-license-prep-snap-tests/)**

It is parked in the personal-brand repo because the 2026-08-05 session that wrote it could not get
push access here, and **it does not run from where it sits** — its `playwright.config.js` serves
`..` and loads `../index.html`, which over there is a different repo. Its intended home is
`snap-tests/` at *this* repo's root, next to `check-bank.py`.

Readable without moving anything: `FINDINGS.md` (results, severity-ranked, with measurements) and
`STATUTE-AUDIT.md` (the Utah law baked into the Snap & Solve prompt, checked against the statute).

The suite has three projects. `functional` (30 tests) is green — red there means a bug in the
harness. `contract` (10 tests) is **red on purpose** — each failure is a finding, and turning it
green is the proof the app got fixed. `live` needs a throwaway `GEMINI_API_KEY` in the environment
and is skipped without one.

## Local preview

It's a static file — open `index.html` directly, or serve the directory over HTTP if you want the
sub-app iframes to behave exactly as they do in production.

## Housekeeping

`*.bak-*` files are local pre-edit backups of `index.html` (~300 KB each) and are gitignored. Don't
commit them.
