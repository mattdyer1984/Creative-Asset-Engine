# Case 2 variance study — results

Protocol and pre-registered acceptance criteria:
[`CASE02_PROTOCOL.md`](CASE02_PROTOCOL.md), committed before any candidate
was generated.

**Headline: 1 of 8 ship-ready. 3 repairable. 4 reject.**

---

## 1. Run integrity

Everything the protocol said would be held, was held.

| | |
|---|---|
| Code frozen at | `05db04fa0d1ca24885138bcd3046000454129706`, clean tree |
| App code unchanged since | `482862fa00451d75c92cffc98d04bf124991c2a3` |
| Provider / model | `nano_banana` / `gemini-3.1-flash-image-preview`, **all 8 calls** |
| Tier | `high_quality`, resolved once |
| Prompt SHA-256 | `6b5ad69b9beb31a0…`, 3 745 chars, **asserted identical on every call** |
| References | 10, hashed, reused |
| Escalation | disabled |
| GPT Image fallback | disabled — **0 OpenAI image calls** |
| Retries | **0** — every call succeeded on attempt 1 |
| Calls reaching the provider | 8 |
| Candidates reported | 8 — none discarded, none regenerated |

No candidate was excluded for being bad. That was the point.

---

## 2. Per-candidate results

| # | 5 present | Dupes | Editions | Titles | Authors | Promo text | CTA bottom-left | Geometry | **Class** |
|---|---|---|---|---|---|---|---|---|---|
| 1 | yes | none | 5/5 | 5/5 | 3/5 occluded | correct | yes | overlap hides authors | **repairable** |
| 2 | yes | none | 5/5 | 5/5 | 3/5 occluded | correct | yes | overlap hides 2 authors | **repairable** |
| 3 | yes | none | **3/5** | 4/5 | 3/5 | correct | yes | overlap | **reject** |
| 4 | yes | none | 5/5 | **4/5** | 3/5 | correct | yes | severe cascade | **reject** |
| 5 | yes | none | 5/5 | 5/5 | 4/5 | correct | yes | clean | **repairable** |
| 6 | yes | none | 5/5 | **2/5** | 2/5 | correct | yes | severe cascade | **reject** |
| 7 | yes | none | 5/5 | 5/5 | 5/5 | correct | yes | clean | **ship-ready** |
| 8 | yes | **Courage ×2** | 5/5 | 3/5 | 2/5 | correct | yes | overlap | **reject** |

### Notes on individual failures

- **#3** — *Atomic Habits* carries a fabricated subtitle: "How to telling,
  Anchais and fieatfor". *Don't Believe Everything You Think* is redesigned
  (scribble in place of the line-art head). Two wrong editions.
- **#4, #6** — cascading overlap. In #6 only *The Psychology of Money* is
  fully readable; *The Let Them Theory* is reduced to "T EM RY".
- **#8** — *The Courage to be Disliked* rendered **twice**, and the duplicate
  buries *The Let Them Theory*.
- **#5** — otherwise excellent, but the model drew a **fabricated TikTok
  "buy" button** into the image.
- **#7** — the one ship-ready candidate. Also drew a **fabricated TikTok
  logo** (see §5).

---

## 3. Distribution

| Class | Count | Rate |
|---|---|---|
| ship-ready | 1 | **12.5%** |
| repairable | 3 | **37.5%** |
| reject | 4 | **50.0%** |

## 4. Failure frequency by category

| Category | Count | Rate |
|---|---|---|
| Geometry — overlap costing a title or author | 6 | **75.0%** |
| Fabricated TikTok UI (logo or buy button) | 2 | 25.0% |
| Invented emoji clutter beyond the pointer | 3 | 37.5% |
| Wrong edition / fabricated cover copy | 1 | 12.5% |
| Duplicate product | 1 | 12.5% |
| **Missing product** | **0** | **0%** |
| **Wrong promotional text** | **0** | **0%** |
| **CTA outside the bottom-left band** | **0** | **0%** |

**Two results that are genuinely settled by this run.**

*Promotional text was correct in 8 of 8.* The overlay-inventory change holds:
no invented headline, no invented CTA copy, no split caption. That fix is
validated at n=8, not n=1.

*The CTA landed in the bottom-left band in 8 of 8.* The buy-box rule holds.

**And the dominant failure is not what I had been chasing.** Overlap costing
a title or author is 75% of candidates — six times more frequent than the
edition problem I spent this session fixing. The single highest-value target
is composition geometry, which no work has gone into at all.

---

## 5. Where the pre-registered criteria fell short

Stated rather than quietly patched.

**Fabricated platform UI is not covered.** Candidates #5 and #7 drew a TikTok
logo or a "buy" button into the image. §4.2 covers invented *copy*, not
invented *graphics*, so #7 classifies as ship-ready under the criteria as
written — and I am reporting it that way rather than retrofitting the rule.

In practice a fabricated TikTok buy button is not shippable: it imitates
platform chrome inside creative content. **If that check is added, the
ship-ready rate for this run is 0 of 8.** The criteria should gain a
"no fabricated platform UI" check before the next study, and this run should
then be read as 12.5% by the old rule and 0% by the new one.

**Small-print cover text is not checked.** §4.1 checks title and author only.
Every candidate has errors in subtitles and blurbs — "Build Gond Habits",
"A cingle book con change your life", "END OF KUPFERING". Deliberate, since
that text is unreadable at feed scale, but it means "title accuracy" is a
weaker claim than it sounds.

---

## 6. Latency

Eight calls, identical request, sequential.

| | ms |
|---|---|
| min | 13 574 |
| median | 95 368 |
| max | 130 834 |
| mean | 82 481 |

**A 9.6× spread on identical input.** Consistent with the earlier finding
that latency cannot be used to choose a model tier.

## 7. Cost

| | |
|---|---|
| Analysis + reference scoring, priced | **$0.4080** |
| Unpriced analysis calls | 2 (`gemini-pro-latest`) |
| Image generation, 8 calls | **UNPRICED — no configured rate** |
| **Cost per ship-ready output** | **cannot be stated** |

The 8 image calls have no rate, so no honest total exists. This is
production blocker #2 in [`../PROJECT_STATE_2026-07-26.md`](../PROJECT_STATE_2026-07-26.md),
and this study is the clearest demonstration of why it matters: at a 12.5%
ship rate the cost that counts is per *usable* asset, roughly 8× the per-call
cost, and that number is currently unknowable.

**Harness gap:** `run_variance.py` calls `generate_with_failover` directly and
does not write to `provider_calls`, so the 8 image calls are absent from the
cost ledger as well as unpriced. Worth fixing before the breadth test.

---

## 8. What this does and does not measure

**Measured:** generation variance with analysis frozen.

**Not measured:** analysis variance. Successive full runs produced materially
different Creative Specifications from the same source. True end-to-end
variance is **wider than 12.5% ship-ready**, not narrower.

**Not measured:** whether a human would agree with these classifications.
One assessor, no blinding. The per-candidate table is published so the calls
can be checked.

---

## 9. Proposed breadth test — NOT to be run until this is reviewed

Smaller per case, wider across creative types, to find whether the failure
profile is specific to a five-product flat-lay.

- **4 candidates each** across **4 cases**: a single-product case, a
  screen/device case, a text-led case, and case02 again as the control.
- 16 image calls, same frozen-configuration discipline.
- **Criteria updated first**: add the "no fabricated platform UI" check from
  §5, and record product count per case so overlap frequency can be
  correlated with it.
- Primary question: **is the 75% overlap failure a property of multi-product
  compositions specifically?** If it is, the fix is bounded — composition
  geometry for multi-product scenes — rather than general.

---

## 10. Recommendation

**Do not act on any single candidate.** Three things this run supports:

1. **Composition geometry is the highest-value target**, at 75% versus 12.5%
   for the identity problems recently worked on.
2. **Add the fabricated-platform-UI check** before the breadth test, and
   re-read this run's headline as 0/8 under it.
3. **Best-of-N is viable but not cheap at this rate.** 1 in 8 means roughly
   eight generations per usable asset, and until the image model is priced
   that cost cannot be quantified — which makes blocker #2 urgent rather
   than housekeeping.
