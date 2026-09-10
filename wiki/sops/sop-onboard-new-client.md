---
title: Onboard a New Client
type: sop
status: example
stage: onboarding
owner: "[[account-manager]]"
last_reviewed: 2026-09-10
review_cycle: quarterly
sources: ["[[src-example-onboarding-notes]]"]
tags: [onboarding, delivery, example]
---

# Onboard a New Client

**Take a signed client from contract to first delivered work, with the account manager
holding the relationship throughout.**

> [!warning] Example content
> Built from a synthetic source. Delete before relying on this wiki.

## Purpose
Convert a signed contract into a working engagement: the client has access, expectations
are set, the delivery team has what it needs, and billing has started. Without it,
delivery starts on guesses and the first invoice slips.

## Trigger
A contract is signed and the deal is announced in the shared channel
[[src-example-onboarding-notes]].

> [!warning] Conflict
> The trigger is unreliable. The source states that Friday signings are sometimes
> missed because the handoff depends on someone noticing a channel message. The
> procedure below assumes the announcement is seen; in practice it is not always.

## Owner and participants
- **Runs it:** [[account-manager]]
- **Consulted:** ops *(inferred — the source has an ops lead in the conversation but does not assign them steps)*
- **Informed:** delivery team, at handoff

## Prerequisites
- Signed contract.
- Deal announced in the shared channel.

## Steps
1. Pick up the signed deal from the shared channel.
2. Send the welcome email the same day where possible. It contains an introduction,
   what happens next, and the intake form link.
3. Collect the intake form: brand assets, access credentials, and the client-side
   day-to-day contact.
4. Chase any missing access credentials. *(inferred — the source names unchased
   credentials as a recurring problem but does not describe a chase step. This step is
   proposed, not observed.)*
5. Set up the client workspace and invite the client contacts.
   > [!question] Open question
   > Who performs this step? The source says it is sometimes the account manager and
   > sometimes ops, and that this is unclear. Assign an owner before this SOP goes
   > `active`.
6. Book and run the kickoff call within the first week. Allow 45 minutes.
7. Send the kickoff recap to the client within 24 hours.
8. Issue the first invoice after kickoff — never before.
9. Hand off to the delivery team once the recap is sent. Remain the relationship owner.

## Definition of done
> [!question] Open question
> Undefined. The source records active disagreement about whether onboarding ends at
> kickoff or at first delivered work. This SOP cannot go `active` until that is ruled
> on, because "done" determines when the delivery handoff is valid.

Candidate end states, for the human to choose between:
- Kickoff call completed.
- Recap sent and delivery team acknowledged the handoff.
- First piece of work delivered and accepted.

## Failure modes and exceptions
| What goes wrong | What to do |
|---|---|
| Deal signed on a Friday and the channel message is missed | No documented mitigation. See open questions. |
| Access credentials arrive incomplete | Nobody currently chases them. Step 4 is proposed, not established practice. |
| Kickoff recap slips past 24 hours | Acknowledged as frequent. No escalation path documented. |

## Handoffs
- **In:** from sales, via the shared-channel announcement.
- **Out:** to the delivery team, once the recap is sent. The account manager does not
  hand off the relationship — only the work.

## Metrics and SLA
| Measure | Target | Source |
|---|---|---|
| Welcome email sent | Same day where possible | [[src-example-onboarding-notes]] |
| Kickoff call booked | Within first week | [[src-example-onboarding-notes]] |
| Kickoff call duration | ~45 min (raised from 30, which was too tight) | [[src-example-onboarding-notes]] |
| Recap sent | Within 24h of kickoff — frequently missed | [[src-example-onboarding-notes]] |

## Related
- [[account-manager]] — owner
- [[agency-profile]]
- [[tools-index]] — the tools used in steps 1, 3, 5, and 8 are undocumented

## Provenance
- Built from: [[src-example-onboarding-notes]] (synthetic).
- Inferred, unverified: the ops consultation in "participants"; the credential-chase
  step (4). Both are marked inline.
- Not stated by any source: payment terms, tool names, escalation paths, what happens
  if the client does not return the intake form.

## Open questions
> [!question] Open question
> Who owns client workspace setup (step 5)?

> [!question] Open question
> Where does onboarding end? Required before a definition of done can be written.

> [!question] Open question
> What are the standard payment terms referenced by "terms are on the contract"?

> [!question] Open question
> What is the escalation path when the kickoff recap slips past 24 hours?
