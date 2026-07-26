# Nano Banana tier comparison — Case 2

**The exact Case 2 production request. Fallback disabled. GPT Image never
touched.** 7,242-character compiled prompt, 8 included reference images.

| | Lite | High quality |
|---|---|---|
| Model requested | `gemini-3.1-flash-lite-image` | `gemini-3.1-flash-image-preview` |
| Model **reported by the provider** | `gemini-3.1-flash-lite-image` | `gemini-3.1-flash-image-preview` |
| Latency | **50,241 ms** | **11,945 ms** |
| Output | 671,131 bytes | 703,495 bytes |
| Cost status | unknown — no configured rate | unknown — no configured rate |

## Latency is not a tier property

The earlier synthetic test showed Lite at 4.6 s and preview at 14.6 s. On the
real payload the order **reversed**: Lite 50.2 s, preview 11.9 s.

Both tiers swing widely for identical work, so **latency cannot be the basis
for tier selection.** That was the error in my first correction.

## Cover-title and author accuracy

| Title | Lite | High quality |
|---|---|---|
| Atomic Habits | title ✅ author ✅; badge garbled | ✅ ✅; **"Over 15 Million Copies Sold" legible and correct** |
| The Psychology of Money | ✅ (author partly occluded) | ✅ (author partly occluded) |
| **The Let Them Theory** | **"THE THEM"** — "LET" lost | ✅ **"LET THEM THEORY" + "MEL ROBBINS"** |
| Don't Believe Everything You Think | partly occluded, author readable | ✅ readable, "EPH NGUYEN" |
| **The Courage to be Disliked** | **corrupted — "habits" bled across from the Atomic Habits cover** | ✅ **"ICHIRO KISHIMI and FUMITAKE KOGA"** — correct, where P1 produced "ICNIRO" |

## Other dimensions

| | Lite | High quality |
|---|---|---|
| Product identity | 5 covers, 2 badly damaged | 4 covers clearly rendered, 1 occluded |
| Layout vs source | fanned spread; source is 3-over-2 | fanned spread; also diverges |
| Realism | good — marble, natural light | good — marble, window light |
| Text bleeding between products | **yes** | no |
| Exact copy in the caption | rewritten | rewritten |

## Verdict

**Case 2 must use the high-quality tier.** Two of five covers are unusable at
the Lite tier — one loses a word from its title, one is contaminated by text
from a neighbouring product. The higher tier rendered the author name that
P1's GPT Image fallback got wrong.

This is a **quality** decision made before generation, not a reaction to a
technical failure.

## Remaining weakness at both tiers

*The Courage to be Disliked* renders **blue** at the high-quality tier; the
real cover is white with a red brush circle. That title is one of the two
without a matching canonical reference — its identity came from crops of the
creative — so this is a reference-coverage gap, not a tier gap.
