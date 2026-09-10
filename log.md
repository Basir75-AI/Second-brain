---
title: Log
type: log
---

# Log

**Append-only chronological record. Newest at the bottom.**
Entry prefix format: `## [YYYY-MM-DD] <op> | <subject>` — see `CLAUDE.md` §7.

```bash
grep "^## \[" log.md | tail -5      # recent activity
```

---

## [2026-09-10] schema | Wiki initialised

- Created `CLAUDE.md` schema: three-layer architecture, folder conventions, page
  anatomy, ingest/query/lint workflows, provenance rules.
- Created `index.md` and `log.md`.
- Created folder skeleton under `raw/` and `wiki/`.
- Created page skeletons in `wiki/_meta/`.
- Open questions raised: agency profile is empty; tool stack undocumented; no service
  lines defined.

## [2026-09-10] ingest | Example onboarding notes (demonstration)

- Source: `raw/2026-09-10-example-onboarding-notes.md` — **synthetic example**, not
  real agency content. Created solely to demonstrate the ingest workflow end to end.
- Created: [[src-example-onboarding-notes]], [[sop-onboard-new-client]],
  [[account-manager]].
- Updated: `index.md`.
- Conflicts flagged: none (no prior content to conflict with).
- Open questions raised: 4, all inside [[sop-onboard-new-client]] — they are the
  questions a real ingest would surface.
- **Cleanup:** all pages above carry `status: example`. Remove with
  `grep -rl "^status: example" wiki/ raw/ | xargs git rm` once the first real source
  is ingested.
