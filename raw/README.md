# raw/ — immutable sources

**The agent never edits or deletes anything in this folder.** This is the source of
truth; the wiki is derived from it.

## How to add a source
1. Drop the file into `raw/inbox/`.
2. Tell the agent: `ingest raw/inbox/<filename>`.
3. The agent reads it, discusses takeaways with you, writes the wiki pages, and moves
   the file to `raw/YYYY-MM-DD-<slug>.<ext>`.

## What belongs here
Meeting notes, call transcripts, client emails, contracts, Slack thread exports, Loom
transcripts, screenshots of tool configuration, existing SOP drafts, process docs,
retro notes, onboarding checklists — anything that records how the agency actually
operates.

## Attachments
Images, PDFs, and exports go in `raw/assets/`. If you use Obsidian Web Clipper, set
Settings → Files and links → "Attachment folder path" to `raw/assets/` so clipped
images land here rather than staying as remote URLs.

## Corrections
If a source contains an error, **do not fix the source.** Tell the agent, and the
correction gets recorded in the wiki with a note about which source was wrong.
