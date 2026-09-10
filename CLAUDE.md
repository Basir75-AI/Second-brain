# CLAUDE.md — Second Brain Schema

This repository is an **LLM-maintained wiki** for the SOPs and operating knowledge of a
service business agency. This file is the schema: it defines the structure, the
conventions, and the workflows. Read it at the start of every session before touching
any file.

**Division of labour.** The human curates sources, directs attention, and asks
questions. The agent writes and maintains *everything* under `wiki/`. The human should
rarely need to edit a wiki page by hand; if they do, that is a signal the schema needs
fixing — offer to update this file.

---

## 1. The three layers

| Layer | Path | Who owns it | Mutable? |
|---|---|---|---|
| Raw sources | `raw/` | Human | **Never modified by the agent.** Read-only source of truth. |
| The wiki | `wiki/` | Agent | Agent creates, edits, refactors, deletes. |
| The schema | `CLAUDE.md` | Both | Co-evolved. Agent proposes changes; human approves. |

Navigation aids at the repo root: `index.md` (content catalog) and `log.md`
(chronological record). Both are agent-maintained.

### Hard rules

1. **Never edit or delete anything under `raw/`.** Not to fix a typo, not to reformat.
   If a source is wrong, note the correction in the wiki, not in the source.
2. **Never invent operational facts.** This wiki describes how a real business runs.
   A fabricated step in an SOP is worse than a missing one, because someone will follow
   it. See §5 (Provenance and confidence) — it is the most important section here.
3. **Every ingest updates `index.md` and `log.md`.** No exceptions.
4. **One source is never one page.** A single ingest typically touches 5–15 wiki pages.
   If an ingest produced one page, the integration work was not done.

---

## 2. Directory conventions

```
raw/                     Immutable sources. Never edited by the agent.
  inbox/                 Drop zone. Unprocessed sources land here.
  assets/                Images, PDFs, screenshots, exports referenced by sources.
  <YYYY-MM-DD>-<slug>.<ext>   Processed sources, moved out of inbox/ on ingest.

wiki/
  sops/                  Executable procedures. The heart of this wiki.
  services/              Service lines / offers the agency sells and delivers.
  roles/                 Role definitions: responsibilities, authority, handoffs.
  clients/               Client and account entity pages.
  tools/                 Software, systems, and platforms the agency runs on.
  policies/              Standing rules and standards that constrain SOPs.
  concepts/              Terminology, metrics, frameworks, cross-cutting ideas.
  decisions/             Decision records: what was decided, when, and why.
  sources/               One summary page per ingested source. The provenance layer.
  queries/               Filed answers to questions worth keeping.
  templates/             Reusable business artifacts (email scripts, brief skeletons).
  _meta/                 Page skeletons and conventions. Not business content.

index.md                 Content catalog. Updated on every ingest.
log.md                   Append-only chronological record.
```

### File naming

- **kebab-case**, lowercase, `.md`. No spaces, no dates in wiki filenames.
- SOPs are prefixed `sop-` and named **verb-noun**: `sop-onboard-new-client.md`,
  `sop-close-monthly-invoicing.md`. The prefix keeps them unambiguous in wikilinks.
- Source pages are prefixed `src-`: `src-q3-onboarding-retro.md`.
- Decision records are prefixed `dec-` and dated: `dec-2026-09-10-move-to-net-14.md`.
- Query pages are prefixed `q-`: `q-which-clients-lack-a-named-owner.md`.
- Everything else uses its plain name: `roles/account-manager.md`,
  `tools/notion.md`, `clients/acme-corp.md`.

### Raw source naming

`raw/YYYY-MM-DD-<slug>.<ext>`, where the date is when the source was **created**
(not ingested) where known, else the ingest date. Keep the original extension.

---

## 3. Page anatomy

Every wiki page opens with YAML frontmatter, then an H1, then a one-sentence summary
in bold, then the body.

```yaml
---
title: Onboard a New Client
type: sop            # sop | service | role | client | tool | policy | concept | decision | source | query
status: active       # draft | active | needs-review | deprecated | example
stage: onboarding    # sales | onboarding | delivery | internal — SOPs only
owner: "[[account-manager]]"
last_reviewed: 2026-09-10
review_cycle: quarterly    # quarterly | semiannual | annual | none
sources: ["[[src-q3-onboarding-retro]]"]
tags: [onboarding, delivery]
---
```

`stage` applies to SOPs only. It places a procedure in the business lifecycle so the
chain from lead to renewal stays visible even as the SOP count grows:

| Stage | Covers | Hands off to |
|---|---|---|
| `sales` | Lead to signed contract: qualification, proposals, pricing. | `onboarding` |
| `onboarding` | Signed contract to first delivered work. | `delivery` |
| `delivery` | How the work actually gets produced, reviewed, and shipped. | `delivery` (recurring) or renewal |
| `internal` | Runs alongside the client lifecycle: invoicing, hiring, tooling, reporting. | — |

Every SOP must name the SOP it hands off to, and the one that hands off to it, in its
**Handoffs** section. Gaps between stages are the most valuable thing this wiki can
surface — report them in every lint pass.

`status` meanings:

- `draft` — written but not verified by a human who runs the process.
- `active` — verified and in force.
- `needs-review` — a newer source contradicts it, or it passed its review date.
- `deprecated` — superseded. Keep the page, add a pointer to what replaced it.
- `example` — demonstration content, not real. Safe to delete.

### Linking

- Use Obsidian wikilinks: `[[sop-onboard-new-client]]`, or `[[tools/notion|Notion]]`
  when the display text should differ.
- **Every page must have at least one inbound link** from another page or from
  `index.md`. Orphans are a lint failure.
- Link the *first* mention of an entity in a page, not every mention.
- When you mention a concept, role, tool, or client that has no page yet, still write
  the wikilink and add the page to the "Pages to create" section of the lint report.
  A red link is a to-do, not an error.

### SOP page skeleton

SOPs carry more structure than other page types because people execute them. Use
`wiki/_meta/sop-skeleton.md`. Required sections:

1. **Purpose** — what this achieves, in one or two sentences.
2. **Trigger** — the event that starts this procedure.
3. **Owner and participants** — who runs it, who is consulted, who is informed.
4. **Prerequisites** — what must be true or in hand before step 1.
5. **Steps** — numbered, atomic, imperative. One action per step. Link the tool used.
6. **Definition of done** — the observable end state. Not "onboarding complete" but
   "kickoff deck sent, access granted, first invoice scheduled."
7. **Failure modes and exceptions** — what commonly goes wrong and what to do.
8. **Handoffs** — what leaves this SOP and where it goes next.
9. **Metrics and SLA** — target duration, quality bar, what is measured.
10. **Related** — links to adjacent SOPs, policies, templates.
11. **Provenance** — sources this page was built from, with what is inferred.
12. **Open questions** — gaps the human needs to fill.

Sections 9 and 12 may be empty, but the headings stay so gaps are visible.

---

## 4. Operations

### 4.1 Ingest

Triggered by: *"ingest raw/inbox/<file>"* or *"process this"*.

1. **Read the source in full.** For markdown with inline images, read the text first,
   then view referenced images in `raw/assets/` separately.
2. **Report back before writing.** Summarise the key takeaways in chat and state your
   proposed plan: which pages you will create, which you will update, and any conflicts
   you found with existing pages. Wait for a go-ahead unless the human said
   "batch ingest" or "don't check in with me."
3. **Write the source page** in `wiki/sources/src-<slug>.md`: what the source is, when
   it is from, who produced it, what it claims, and what it changes in the wiki.
4. **Integrate.** This is the actual work. For each entity, procedure, tool, role, or
   policy the source touches:
   - Create the page if it does not exist.
   - Update the page if the source adds, sharpens, or dates a claim.
   - **Flag contradictions explicitly** — do not silently overwrite. See §5.
   - Add cross-references in both directions.
5. **Move the source** from `raw/inbox/` to `raw/` with the naming convention.
6. **Update `index.md`** — add new pages, revise one-line summaries that changed.
7. **Append to `log.md`.**
8. **Report** what you touched: created, updated, flagged, and what you could not
   resolve.

### 4.2 Query

Triggered by any question about the business.

1. Read `index.md` first to locate candidate pages. Then read those pages.
2. Answer with **citations to wiki pages**, which themselves cite sources. If the
   answer rests on something inferred rather than sourced, say so in the answer.
3. If the wiki cannot answer it, say so plainly and name what source would fill the
   gap. Do not fill the gap with plausible-sounding general agency advice.
4. **Offer to file the answer.** Good answers — comparisons, gap analyses, synthesis
   across several SOPs — belong in `wiki/queries/` as `q-<slug>.md`, so exploration
   compounds instead of evaporating into chat history. File it if the human agrees,
   then update `index.md` and `log.md`.

### 4.3 Lint

Triggered by: *"lint the wiki"*.

Produce a report covering:

- **Contradictions** — pages that disagree with each other.
- **Stale pages** — `last_reviewed` older than `review_cycle`, or superseded by a
  newer source.
- **Orphans** — pages with no inbound links.
- **Missing pages** — red wikilinks, and concepts referenced repeatedly with no page.
- **Thin SOPs** — SOPs missing a definition of done, an owner, or steps.
- **Unsourced claims** — operational claims with no provenance and no `(inferred)` tag.
- **Coverage gaps** — service lines with no SOPs, SOPs with no named owner, roles
  with no linked procedures.
- **Suggested next sources** — what the human should capture next, ranked.

Write the report to chat. Only change files if the human asks. Never auto-delete a page.

### 4.4 Schema evolution

If a convention here is not working, say so and propose a specific edit to this file.
Do not silently deviate from the schema.

---

## 5. Provenance and confidence

This is an operations wiki. People will act on it. Accuracy outranks completeness.

**Every operational claim traces to one of three states, and the page must show which:**

1. **Sourced** — supported by a source. Cite it inline: `Net-14 payment terms [[src-2026-client-agreement]].`
2. **Inferred** — the agent's reasonable reconstruction, not stated in any source.
   Mark it inline: `Invoices are approved by the account lead *(inferred)*.`
3. **Unknown** — mark the gap rather than filling it:
   ```
   > [!question] Open question
   > Who approves discounts above 15%? No source covers this.
   ```

Additional rules:

- **Never invent** tool names, integrations, plan tiers, prices, client names, staff
  names, legal or tax rules, or numeric thresholds. If a source does not say it, it is
  an open question.
- **Flag every number** that did not come from a source, and say so in chat too.
- **Contradictions get a callout, not a silent overwrite:**
  ```
  > [!warning] Conflict
  > [[src-2026-06-sales-playbook]] says discovery calls are 30 min;
  > [[src-2026-09-onboarding-retro]] says 45 min. Newer source assumed correct;
  > needs a human ruling.
  ```
  Then set `status: needs-review` and list it in the next lint report.
- **Recency matters more than usual here.** Business processes change. When two sources
  disagree, prefer the newer one *and say that you did.*
- If a page's claims rest mostly on inference, its `status` is `draft`, never `active`.

---

## 6. Working style

- Prefer **updating an existing page** over creating a near-duplicate. Search first.
- Keep SOP steps **atomic and imperative**: "Send the kickoff deck," not "The kickoff
  deck should then be sent to the client by someone."
- Prefer **specific over general**. "Reply within one business day" beats "reply
  promptly." If the source is vague, keep the vagueness and mark it an open question
  rather than inventing precision.
- Do not pad. A 6-step SOP that is accurate beats a 20-step one that is half guessed.
- Do not write general agency best-practice advice into the wiki. This wiki records
  *how this agency actually works*, not how agencies in general should work.
- When the human asks a question mid-ingest, answer it before continuing.

---

## 7. Log format

`log.md` is append-only. Newest entries at the bottom. Every entry starts with a
consistent prefix so the file stays greppable:

```
## [YYYY-MM-DD] <op> | <subject>
```

where `<op>` is one of `ingest`, `query`, `lint`, `refactor`, `schema`.

Useful commands:

```bash
grep "^## \[" log.md | tail -5           # last 5 operations
grep "^## \[" log.md | grep ingest       # every ingest
grep -rl "status: needs-review" wiki/    # pages needing a human ruling
grep -rn "(inferred)" wiki/sops/         # every inferred claim in the SOPs
grep -rn "\[!question\]" wiki/ | wc -l   # open question count
```

Each entry body lists: source ingested (if any), pages created, pages updated,
conflicts flagged, and open questions raised.

---

## 8. Session start checklist

1. Read this file.
2. Read `index.md`.
3. Run `grep "^## \[" log.md | tail -5` to see recent activity.
4. Check `raw/inbox/` for unprocessed sources.
5. Then start work.
