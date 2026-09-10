---
title: Example Onboarding Handoff Notes
type: source
status: example
source_file: "raw/2026-09-10-example-onboarding-notes.md"
source_date: 2026-09-10
source_kind: meeting-notes
author: ops lead + account manager (synthetic)
ingested: 2026-09-10
tags: [onboarding, example]
---

# Example Onboarding Handoff Notes

**Synthetic meeting notes describing how a signed client moves from contract to first
delivered work. Used to demonstrate the ingest workflow — not real agency content.**

> [!warning] Example content
> This source and every page derived from it are synthetic. Delete before relying on
> this wiki: `grep -rl "^status: example" wiki/ raw/ | xargs git rm`

## What this is
Informal notes from a discussion between an ops lead and an account manager about the
client onboarding handoff, capturing both the current process and its known problems.

## Key takeaways
- Onboarding runs sales → account manager → delivery team, with the account manager
  retaining the relationship after handoff.
- The sequence is: signal in shared channel → welcome email + intake form → workspace
  setup → kickoff call → recap → first invoice → delivery handoff.
- Three failure points were named explicitly: Friday signings get missed, kickoff
  recaps slip past 24 hours, and incomplete access credentials go unchased.
- Ownership of client workspace setup is genuinely undefined — the source says so.

## Claims extracted
| Claim | Confidence | Where it landed |
|---|---|---|
| Signed deals are announced in a shared channel | sourced | [[sop-onboard-new-client]] |
| Welcome email sent same day where possible | sourced | [[sop-onboard-new-client]] |
| Intake form collects assets, access, day-to-day contact | sourced | [[sop-onboard-new-client]] |
| Kickoff booked within first week, runs ~45 min | sourced | [[sop-onboard-new-client]] |
| Kickoff was previously 30 min, lengthened as too tight | sourced | [[sop-onboard-new-client]] |
| Workspace setup owner is undefined | sourced (as a gap) | [[sop-onboard-new-client]] |
| Recap target is 24 hours, frequently missed | sourced | [[sop-onboard-new-client]] |
| First invoice issued after kickoff | sourced | [[sop-onboard-new-client]] |
| Payment terms live on the contract | sourced (unspecified) | open question |
| Account manager owns the relationship post-handoff | sourced | [[account-manager]] |
| "Onboarded" has no agreed definition | sourced (as a gap) | [[sop-onboard-new-client]] |

## Conflicts with existing pages
None — this was the first source ingested into an empty wiki.

Note for future ingests: this source records that kickoff length changed from 30 to 45
minutes. If an older source states 30 minutes, that is a superseded claim, not a
conflict, and the older page should be updated with a pointer here.

## Pages touched
- Created: [[sop-onboard-new-client]], [[account-manager]]
- Updated: `index.md`, `log.md`

## Open questions raised
> [!question] Open question
> Who owns client workspace setup — account manager or ops? The source explicitly says
> this is undefined. It is the single highest-value gap in this SOP.

> [!question] Open question
> Where does onboarding end: at kickoff, at recap sent, or at first delivered work?
> Without a ruling, the definition of done cannot be written.

> [!question] Open question
> What are the standard payment terms? The source defers to "the contract" without
> stating them.

> [!question] Open question
> Which tools are used for the shared channel, intake form, client workspace, and
> invoicing? The source names none. See [[tools-index]].
