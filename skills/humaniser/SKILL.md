---
name: humaniser
description: Use when rewriting AI-drafted prose so it reads as human-written, or when the user says a message sounds AI-generated, robotic, templated, "off", or specifically complains about em dashes or sentences all sounding the same length. Applies to cold emails, job-search messages, docs and general writing, with treatment calibrated per register; it must not make technical writing chatty.
---

# Humaniser

## Why AI prose reads as AI

LLMs decode towards the statistical centre of their training distribution: the most probable next word, the safest transition, the most common way to open a paragraph. Detectors built on this fact (DetectGPT, Binoculars, Ghostbuster) score text on **perplexity** (how predictable each word choice is) and **burstiness** (how much that predictability swings sentence to sentence). Human writing is bursty: perplexity spikes and dips because people get specific, then casual, then terse. AI text is flat, consistently probable, consistently smooth, consistently the same shape.

Two consequences the user will actually notice:

1. **Uniform sentence length.** No local reason to vary rhythm produces one. Human writing is bursty because attention and memory are: a long explanatory sentence gets followed by a short correction, a fragment, a plain statement.
2. **Signature punctuation and connective tissue.** The em dash is a cheap way to bolt two clauses together without deciding how they relate. A comma, full stop, or parenthesis all force a sharper choice, so models default to the dash instead. The same laziness shows up as "not just X, but Y", stacked hedges, and explicit signposting ("Furthermore", "It's worth noting").

Caveat on the evidence: commercial detectors (GPTZero included) mostly moved off raw perplexity/burstiness to learned classifiers around 2023. Treat this as an explanatory model of *why prose reads as machine-written to a person*, not a scoring formula for beating a specific tool. The goal is prose a human would actually write, not a number.

Most public "humaniser" prompts are just banned-word lists (never say "delve", "leverage", "tapestry") with no theory. That catches nothing that matters: a single instance of any of those words is invisible. It's the *pattern* that reads as AI, flat rhythm, clustered tics, mechanical structure. Rules below target the pattern, not the vocabulary alone.

## Register first: this is not one register

| Register | Target shape | What NOT to do |
|---|---|---|
| Cold email / job-search message | Terse, varied, one ask. See the `cold-outreach` skill for structure rules; this skill fixes *how it reads*, that one fixes *what it says*. | Don't add warmth or hedging to pad length |
| Technical doc / README | Plain, precise, short sentences by default. Burstiness still applies but the "long" end is shorter. | Don't inject first person, contractions-as-personality, or rhetorical flourish; that reads as worse, not more human |
| Message to a friend / colleague | Fragments, contractions, low formality. | Don't over-correct into forced casualness. One deliberately dropped subject per message is plenty |
| Formal document (cover letter, report) | Full sentences, contractions used sparingly, no fragments. | Don't apply the fragment/contraction rules below: this register can look AI in other ways (empty adjectives, false triads), not via rhythm alone |

Decide the register before applying anything below. A technical doc rewritten "human" by making it chatty is a worse document, not a better one.

## Rule 1: sentence-length variance (the biggest lever)

Flat sentence length is the single strongest tell; fixing it does more than every vocabulary rule combined.

- Classify every sentence as **short** (3–8 words), **medium** (12–20), or **long** (25–40+).
- In any run of five consecutive sentences, at least one must be short and at least one must be medium-or-long. Three sentences in a row landing within roughly 4 words of each other's length is a fail; rewrite one of them.
- Fragments count as legitimate short sentences in informal/email registers. Not in formal documents or technical docs.
- This is a paragraph-level rule, not a whole-document average: a document can average variance while every paragraph is monotone. Check each paragraph.

Compressed cold emails (2–4 sentences total) can't hit "five in a row"; apply the spirit instead. Don't let every sentence in the message land within a few words of the others.

## Rule 2: punctuation, especially the em dash

- **Default: zero em dashes** in cold outreach, job-search messages, and casual registers. The dash isn't inherently a tell; its *elevated rate* relative to normal human writing is. At this length there's no room for a rare legitimate use, so cut it outright and pick the relationship it was hiding: cause (full stop, new sentence), aside (parentheses), or list (comma).
- **Long-form/technical registers:** a genuine parenthetical is fine occasionally. If you're reaching for a second one in the same document, that's the tell: go back and decide what the clauses actually mean to each other.
- Semicolons: use only where the two clauses are genuinely balanced and independent. AI overuses them to avoid ending a sentence; if in doubt, end the sentence.
- No curly/smart quotes introduced deliberately, no decorative bold, no title-case headings where sentence case is normal for the register.

## Rule 3: banned constructions (flag by cluster, not by single instance)

A lone hit of any of these is invisible. Two or more in the same paragraph, or a pattern repeated across the document, is the actual signal.

| Construction | Why it reads as AI | Fix |
|---|---|---|
| "It's not just X, it's Y" | Manufactures contrast instead of adding information | State the fact plainly |
| Rule of three ("fast, reliable, and scalable") | Rhythm imposed regardless of whether three things are true | Cut to what's actually true; two or four is fine |
| Staged run-ups ("In today's fast-paced world…", "Let's dive in") | Generic scene-setting that delays the point | Open with the fact |
| Explicit signposting ("Furthermore", "Moreover", "It's worth noting that", "In conclusion") | Humans rely on paragraph breaks and word order, not labelled transitions | Cut it; the next sentence should carry its own weight |
| Stacked hedges ("may potentially suggest a possible…") | Each hedge alone is fine; three in a row is reflexive caution | Keep one hedge, or none |
| Copula avoidance ("serves as", "stands as a testament to", "represents a shift towards") | Inflates a plain "is" into false significance | Use "is" / "has" |
| Dramatic one-line closer ("And that changes everything.") | Manufactured importance with no new fact | Cut the sentence |
| AI vocabulary cluster (delve, tapestry, testament, pivotal, leverage, robust, landscape, underscore, multifaceted) | Individually unremarkable; clustered, they're a fingerprint | Plain verb or noun instead |
| Rebutting an objection nobody raised ("Some might argue X, but…") | Manufactured tension to sound balanced | Delete unless the objection is real and specific |

## Rule 4: rhythm and register mechanics

- **Contractions:** use in email/casual/friend registers; use sparingly in formal documents; avoid manufacturing them in technical docs where they weren't natural.
- **Fragments:** one or two per informal message is human, not sloppy. Zero in technical docs and formal documents.
- **Paragraph length:** vary it. A document where every paragraph is 3–4 sentences is itself a flatness tell, independent of sentence length inside them.
- **Specificity beats hedged generality:** a real number, name, or date reads as human because it's the kind of detail a template can't produce. Never invent one to satisfy this; flag the gap instead (see Guardrail below).

## Guardrail: never fabricate

Rewriting for rhythm and punctuation must never add facts, numbers, names, dates, or claims that weren't in the source. If a rule above would be better satisfied by a specific detail that doesn't exist yet, say so and ask, rather than inventing one.

## Self-check: run on your own output before returning it

1. List every sentence's word count, per paragraph. Confirm Rule 1 (no three in a row within roughly 4 words of each other; short plus medium-or-long present per five-sentence stretch, or the compressed equivalent for short messages).
2. Count em dashes. Cold/casual register: must be 0. Long-form/technical: flag if more than roughly one per 300 words, or more than one in the same document if each is meant to be rare.
3. Scan against the Rule 3 table. A single hit anywhere is fine. Two or more from the table in one paragraph, or the same one repeated across the document, means rewrite.
4. Confirm the register table above was actually applied. A technical doc that picked up fragments or first-person asides has been over-corrected, not fixed.
5. Confirm no fact, number, or name was added that wasn't in the source.

## Before / after

**Cold email opener (AI draft):**
> I hope this message finds you well. I wanted to reach out because I was really impressed by your work at Acme, and I believe my background in backend engineering would be a great fit for your team. I have experience in Python, distributed systems, and cloud infrastructure — and I'm confident I could add value from day one.

**Humanised:**
> Saw your talk on Acme's event-sourcing migration last week. The bit about replaying six months of Kafka logs in prod took nerve. I've done something similar, cutting a reconciliation job from a day to under an hour. Worth a fifteen-minute call?

Sentence lengths: 9, 13, 15, 4. Genuinely bursty, and zero em dashes, unlike the draft above (its dash is left in deliberately, as the tell being fixed).

**Technical doc line (AI draft):**
> This function serves as a robust utility that handles a multitude of edge cases, ensuring seamless integration and providing a comprehensive solution for data validation.

**Humanised (still technical register, not made chatty):**
> Validates input against the schema and rejects anything malformed. Null, empty string, and out-of-range values are handled as separate cases below.

No contractions added, no first person, no fragments: this register doesn't want them. The fix is cutting the copula avoidance and inflation, not injecting personality.

## Evidence base

- Wikipedia, [*Signs of AI writing*](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing): community-curated corpus of the exact constructions in Rule 3, and the single best free evidence base for what actually recurs.
- GPTZero, [*What is perplexity & burstiness?*](https://gptzero.me/news/perplexity-and-burstiness-what-is-it/): plain-language definitions of the two metrics underlying Rule 1, and the source for the caveat that GPTZero itself moved to a learned classifier post-2023.
- [blader/humanizer](https://github.com/blader/humanizer): best available theoretical frame ("staging vs stating") and the practice of ranking tells by strength, acting on one sighting of a strong tell while treating weak tells as meaningful only clustered. The strongest of the public Claude-skill humanisers on conceptual grounds.
- [Aboudjem/humanizer-skill](https://github.com/Aboudjem/humanizer-skill): most rigorous of the public options. It has a real weighted self-check formula (lexical, repetition, burstiness, diversity), tiered rather than flat banned-word lists, numeric burstiness bands, and an unusual explicit "what not to flag" list to avoid false positives on non-native English, short samples, and technical jargon. Best on the market for operational rigour; Rules 1 and 3 and the self-check above draw directly on it.
- [matsuikentaro1/humanizer_academic](https://github.com/matsuikentaro1/humanizer_academic): useful sentence-length standard-deviation framing (human writing roughly 10–15 words, AI under 5) but its headline "~90% of achievable AI-score reduction" claim rests on a single unsourced internal metric ("desklib logit") with no published methodology. Took the framing, left the percentage out.
- [harshaneel/humanize](https://harshaneel.github.io/humanize/): genuinely cites real detection literature (DetectGPT, Binoculars, Ghostbuster, watermarking), which grounds the mechanism section above. Its precise numeric thresholds (for example, em dashes at "3–5x baseline") are plausible but not independently verified here, so they're used as directional support rather than a cited fact.

**Left out as folklore:** absolute "zero em dashes, ever, in all writing" rules. The dash isn't the tell; an elevated *rate* is, and long-form registers have legitimate rare uses. Flat banned-word lists with no clustering logic: a single "delve" is not a tell. Blanket "always use contractions / short sentences" advice: register-blind, and would wreck a technical doc or formal letter.
