# Second Brain — Agency SOP Wiki

An LLM-maintained knowledge base for the operating knowledge and SOPs of a service
business agency. Built on the [LLM Wiki](https://github.com/) pattern: raw sources stay
immutable, the agent compiles and maintains a structured wiki on top of them, and the
knowledge compounds with every source instead of being re-derived on every question.

## Layout

```
CLAUDE.md    The schema. Rules the agent follows. Read this first.
index.md     Catalog of every page.
log.md       Chronological record of every operation.
raw/         Immutable sources. The agent reads these and never edits them.
wiki/        Agent-owned markdown. You read it; the agent writes it.
```

## How to use it

| You want to | Say |
|---|---|
| Add knowledge | Drop a file in `raw/inbox/`, then: `ingest raw/inbox/<file>` |
| Ask a question | Just ask. The agent reads `index.md`, then the relevant pages. |
| Keep a good answer | `file that answer` — it becomes a page in `wiki/queries/`. |
| Health-check the wiki | `lint the wiki` |
| Change how it works | `update the schema so that ...` |

## Reading it

The wiki is plain markdown with Obsidian-style `[[wikilinks]]`. Open the repo folder as
an Obsidian vault to browse it with backlinks and graph view. Nothing here depends on
Obsidian — it is a git repo of markdown files.

## Ground rules the agent follows

- It never edits anything under `raw/`.
- It never invents operational facts. Unsourced claims are marked `*(inferred)*`;
  unknowns become `> [!question]` callouts instead of plausible filler.
- Contradictions between sources get flagged, not silently resolved.
- Every ingest updates `index.md` and `log.md`.

Full rules: [`CLAUDE.md`](CLAUDE.md).
