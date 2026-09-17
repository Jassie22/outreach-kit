---
name: cold-outreach
description: Use when writing cold or warm outreach to recruiters, in-house talent teams, hiring managers or founders — job-search emails, LinkedIn messages, follow-ups and chasers. Enforces evidence-only claims, per-audience structure, and hard length and content limits.
---

# Cold outreach to recruiters and hiring contacts

> **Set this up before first use.** Anywhere you see `FILL IN`, replace it with
> your own. The structural rules below are general; the tone rules have to be
> yours, because a skill carrying someone else's voice will write someone
> else's emails.

## Before writing anything

1. **Read your applicant reference file.** `FILL IN: path, e.g. ~/notes/applicant-reference.md`. One file holding years of experience, titles, salary expectation, and an explicit do-not-claim list. **Never state anything it does not support.** This is what stops an eager model inventing a framework you have never used.
2. **Identify the lane** — agency consultant / in-house talent / founder / warm inbound. They want genuinely different things and a message in the wrong register reads as spam.
3. **Check your contact list** for prior contact, so nobody gets two cold emails.
4. **Personalise to the depth the lane needs** (rule 10 below).

## The four lanes

| Lane | Wants | Wastes their time |
|---|---|---|
| **Agency consultant** | Filter fields, fast: title, stack, location, notice, right to work. Paid on placement, optimising time-to-fill. | Narrative, motivation, career story. "Open to opportunities" is useless to them |
| **In-house talent** | Role fit *and* "why this company". Owns the req and the brand. | Generic blasts with no sign you know what the company does |
| **Founder / eng lead** | Whether you can solve a problem they have now. Under ~50 people the founder usually *is* the hiring manager. | CV-speak, pedigree, HR register. Talk peer-to-peer and technical |
| **Warm inbound** | A direct answer to what they asked. | The cold structure. Do not pitch at someone who already initiated |

## Effort is not evenly spread

| Lane | Effort | What that means |
|---|---|---|
| **Founder / eng lead** | Highest | Research the company before writing. The opener is bespoke. Budget real time per message. |
| **In-house talent** | Medium | Lane template, plus an opener naming the company and one concrete reason it is them. |
| **Agency consultant** | Lowest | Lane template, plus an opener naming their desk. They are scanning for filter fields. Do not over-invest. |

Templates live in `templates/`: `a*` agency, `f*` founder, `h*` in-house. Each is a lane variant with an `{opener}` slot. Rotate templates across a batch and write the opener fresh every time. `check_variation.py` fails the build if two same-lane templates drift too close together.

## Writing the founder opener

Founders built the thing and care about it far more than they care about a CV. The founder opener is **two or three sentences** doing three jobs in order:

1. **Name the specific thing** — the product, a feature they shipped, the round they raised, the problem they chose. Pull it from the `notes` field on their row, which should carry a verifiable fact and a URL.
2. **Say something real about it** — an observation only someone who looked would make. What is technically hard, what the interesting decision was.
3. **Say why the email exists** — that you are looking for your next role and they came up.

**A genuine observation, never flattery, never a sales opener.** The test: could this sentence be sent to any other company? If yes, it has failed.

- Good: *"I came across [company] and the approach of training agents from screen recordings rather than APIs stood out, mostly because it sidesteps the integration problem everyone else is stuck on."*
- Failed: *"I'm really impressed by the innovative work you're doing at [company]."*

Never compliment something you have not verified. No opener, no send: the sender skips an incomplete row and retries it next run.

## The closing question, founder lane

**A short, bare question about their technology or their business.** Eight to fifteen words. No lead-in, no framing, and **no reference to what you have built** — the evidence block already did that job, and repeating it reads as a pitch.

- Good: *"Which part of the ingestion pipeline breaks most often?"*
- Good, business rather than tech: *"Are customers switching off an incumbent, or off spreadsheets entirely?"*
- Failed, too long and self-referential: *"I spent four months on real-time dashboards, so I'm genuinely curious what your latency budget is."*
- Failed, forced: *"Out of curiosity, what's the hard part?"*

It should be answerable in one sentence by someone who built the thing, and it should be a question only someone who looked at the product could ask. If no real question exists, a plain close beats a forced one. Never repeat a phrase from the opener in the question; check for it.

## Structure

**Three blocks, blank line between each:**

1. **Why this email exists.** Open by saying why it landed in their inbox. Not your name (it is in the From field and the sign-off), not a greeting formula.
2. **Evidence.** Flowing prose, no bullets. Strongest skill first, then supporting ones, then two or three concrete things you built.
3. **Ask, as a question.** Every message ends on a question or an open door.

**Sign-off: `FILL IN` — just your first name is usually right.** Never "Kind regards", never a signature block.

### Hard tone rules

These are the ones that generalise. Add your own as you correct the model; every rule below started as somebody's correction.

- **Never state years of experience.** It is the weakest fact about you. The CV says it once, in context, after they have read what you built.
- **Never mention location** unless it is genuinely useful, and then only as flexibility: *"happy to relocate"*, *"flexible on location"*. Never as a constraint, never as its own paragraph.
- **Never write "available immediately"** or "available now". It reads as *please*. If they want a start date they will ask, and then it is good news.
- **Never sound apologetic about your tools.** State how you work as fact.
- **Never sound desperate.** One open question is enough. Do not stack "in case anything suits" with "still looking".
- **No name introduction.** "I'm X, a backend engineer" is redundant in email.
- **Zero em dashes.** Run the `humaniser` self-check if unsure.
- `FILL IN: your own corrections go here as you make them.`

### Subject lines

A question, or a specific noun about them. Sentence case. Under 7 words.

**Never:** `Application for [Role]` (routes to a folder) · your own name (already in From) · `Opportunity` / `Introduction` / `Networking` · Title Case · anything over 7 words.

**Founder subjects must be honest about intent.** A technical-question subject followed by a job pitch is bait-and-switch and a founder will spot it. Say you are asking about roles; put the genuine technical question at the *end* of the body.

### Your voice

`FILL IN.` The best source is **your own sent mail**, not cold-email advice. Pull ten emails you actually sent and note what recurs: sentence length, whether you use contractions, how you open, how you sign off, whether you ask questions back. Write those observations here. Cold-email research will tell you what works on average; your sent folder tells you what sounds like you.

**Length: 90–150 words.**

## Hard rules

1. Length caps above. No exceptions.
2. **Never open with** "I hope this finds you well", "My name is X and I'm reaching out", "I came across your profile", or any line sendable unchanged to 1,000 people.
3. **First sentence carries a recipient-specific trigger.**
4. **Open by saying why the email exists**; put the ask at the END, as a question.
5. **Never state years of experience.** Lead with your strongest skill, then what you built.
6. **No salary number unprompted.** A rough figure is permitted *only* in the agency lane, where it is a filter field.
7. **Don't apologise for your background** — no "despite", no "even though I don't have".
8. **No self-adjectives**: passionate, motivated, results-driven, proven track record.
9. **Numbers over adjectives**, always.
10. **Personalisation depth is lane-dependent.** Agency: naming their desk is enough, they are a matching service. In-house and founders: one specific verifiable fact is required. Never invent a fact to fill the slot.
11. **One contact per company.** Two people at the same firm share a CRM and will see both.
12. **Match the CV to the message.** If the message claims it, the CV shows it.

## Attachments

Cold-email convention says link rather than attach. Against that: agency consultants work CV-first and cannot submit you without one, and a founder who has to click through to a portfolio to decide whether you are worth a reply mostly does not click.

`FILL IN: your call.` Attaching in every lane is a defensible default. Whatever you choose, be consistent, and make sure the templates match — an email that says "happy to send a CV over" with the CV attached reads as careless.

## Follow-ups

- **One follow-up, after 5–7 business days.** Not sooner.
- **Maximum two follow-ups total.** Sales-sequence data showing 4–9 touches is automated outreach to hundreds of leads, a different social contract. To a named human it reads as harassment.
- **Every follow-up adds one new fact.** A bare "just checking in" is banned.
- For a **stalled process**, give them an easy out: *"Even a no is useful, I'm planning around a couple of other processes."* This converts non-replies into replies.

## Warm inbound — different rules entirely

- **Reply within one business day.**
- Thank them, answer directly, ask a clarifying question if their message was thin.
- **Do not lead with a proof-point pitch.** They already initiated; the advantage is spent by re-pitching.
- Even a "not for me" stays short and warm. The relationship is the asset.

## Quality checklist — run before every send

- [ ] Every claim traceable to your reference file
- [ ] Subject is a question or specific noun about them, sentence case, under 7 words
- [ ] 90–150 words
- [ ] Opens by saying why the email exists
- [ ] No years of experience, no location as a constraint, no "available immediately"
- [ ] Zero em dashes; run the `humaniser` self-check if unsure
- [ ] Evidence block is prose, no bullets
- [ ] Ends on a question or an open door
- [ ] No banned openers, no self-adjectives, no apology framing
- [ ] No unprompted salary outside the agency lane
- [ ] Correct CV attached, or deliberately linked
- [ ] Logged in your contact list with today's date

## Drafting behaviour

- **Create drafts, never send**, unless the user explicitly approves that specific message.
- In bulk, **show one full example and get tone approval before generating the rest**.
- Run `send.py --dry-run` and read the output before ever passing `--send`.
