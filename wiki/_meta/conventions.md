---
title: Conventions Cheatsheet
type: meta
---

# Conventions Cheatsheet

Quick reference. `CLAUDE.md` at the repo root is authoritative.

## Naming
| Kind | Pattern | Example |
|---|---|---|
| SOP | `sop-<verb>-<noun>.md` | `sop-onboard-new-client.md` |
| Source | `src-<slug>.md` | `src-q3-onboarding-retro.md` |
| Decision | `dec-YYYY-MM-DD-<slug>.md` | `dec-2026-09-10-move-to-net-14.md` |
| Query | `q-<slug>.md` | `q-which-sops-lack-owners.md` |
| Entity | `<name>.md` | `account-manager.md`, `acme-corp.md` |
| Raw source | `YYYY-MM-DD-<slug>.<ext>` | `2026-09-10-kickoff-notes.md` |

## Status values
`draft` · `active` · `needs-review` · `deprecated` · `example`

## Confidence markers
| Situation | Write |
|---|---|
| Backed by a source | `Net-14 terms [[src-client-agreement]].` |
| Agent's reconstruction | `Approved by the account lead *(inferred)*.` |
| Not known | `> [!question] Open question` callout |
| Two sources disagree | `> [!warning] Conflict` callout + `status: needs-review` |

## Useful greps
```bash
grep "^## \[" log.md | tail -5           # recent activity
grep -rl "status: needs-review" wiki/    # pages awaiting a human ruling
grep -rn "(inferred)" wiki/sops/         # unverified claims in SOPs
grep -rn "\[!question\]" wiki/           # every open question
grep -rl "^status: example" wiki/ raw/   # demo content, safe to delete
```

## Note on placeholder links
`wiki/_meta/`, `CLAUDE.md`, and `README.md` contain illustrative wikilinks
(`[[src-...]]`, `[[<role>]]`, `[[notion]]`) that intentionally do not resolve. They are
documentation examples, **not** to-dos. A lint pass should ignore red links originating
in these files and report only those inside real content pages.
