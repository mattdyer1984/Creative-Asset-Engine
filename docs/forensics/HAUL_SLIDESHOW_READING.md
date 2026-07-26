# Reading the £20 haul slideshow

Slideshow `cc1476d5`, 8 slides, imported 2026-07-26 19:52. Read from stored
artefacts and the source images. No paid generation.

Two columns throughout: **what the creative is actually doing**, and **what
the system stored**. The gap between them is the answer to your questions.

---

## The blocking finding, first

**Every slide from 1 to 7 was assigned to a product named "Security Check".**

```
slide 0 | (none)          |
slide 1 | Security Check  | primary
slide 2 | Security Check  | primary
...
slide 7 | Security Check  | primary
```

"Security Check" is TikTok's bot-block page. The product importer hit that
wall, took the page title as the product name, and created a product from it.
There are now **three** such products in the database, one from this run, and
it carries **25 reference images**. Sixteen images were generated against it.

So the seven distinct beauty products in this haul were all treated as one
phantom product. Nothing downstream could possibly have got the identities
right, because the system believed every slide showed the same thing.

That single fact determines the answer to question 6 below.

---

## 1. Overall purpose

**A budget-credibility haul whose real job is to sell one item — the lash
growth serum — by burying it at the end of six honest recommendations.**

The £20 constraint is the persuasion device. By proving six genuinely cheap
finds first, the creator earns the authority to make the seventh
recommendation, which is the only one carrying a CTA and urgency.

**The system's own arc summary gets this right:**

> "The slideshow uses a budget-shopping ranking format to hook viewers, then
> walks through a series of beauty finds in ranked order. It ends by
> spotlighting a lash growth serum with urgency around a sale, functioning as
> **the main promotional push**."

That is a correct reading. The comprehension exists.

## 2. The story

A countdown with a withheld payoff.

> "I had only £20. Here is what I got, ranked. Number seven is the one you
> actually need, and it's on sale."

The ranking creates a reason to keep swiping — you cannot know what #7 is
without reaching it. The rising numbers are a promise that the best is last.

## 3. Role of each slide

| # | Content | Role | System's stored `beat` |
|---|---|---|---|
| 0 | £20 note on oak, "Ranking what I got today with only £20 to spend…" | **Premise and constraint.** Sets the budget that makes everything after it impressive | `hook` ✓ |
| 1 | MUA Glow Drops highlighter | Ranked item — proof of thrift | `story` ✓ |
| 2 | BYOMA retinol oil (diptyque candle behind) | Ranked item | `story` ✓ |
| 3 | Dr. PAWPAW balm | Ranked item | `story` ✓ |
| 4 | Spectrum A10 blusher brush | Ranked item | `story` ✓ |
| 5 | ISOCLEAN brush cleaner, "5.😭" | Ranked item; the emoji adds personality | `story` ✓ |
| 6 | Grow Gorgeous hair density serum | Ranked item — highest-value so far, raises the stakes | `story` ✓ |
| 7 | "glow for it" lash growth serum, "7!! 🥺", "Sale ends soon 👀 👇👇👇" | **The payoff and the only commercial ask** | `cta` ✓ |

The beat structure was captured correctly on all eight slides.

## 4. Which slide introduces the promoted product

**Slide 7.** It is the only slide with urgency ("Sale ends soon"), the only
one with a buy-box pointer (three 👇 bottom-left), and the only one whose
number carries emphasis ("7!!" rather than "7.").

Slides 1–6 introduce products, but none of them is *promoted*. They are
evidence.

## 5. Which products are incidental

Two distinct kinds, and the difference matters:

**Incidental as props** — never the subject, replaceable with anything:
- the diptyque Baies candle behind the BYOMA bottle (slide 2)
- the dark object top-left of slide 0
- the surfaces themselves: oak table, white marble, grey curtain

**Incidental to the commercial goal but essential to the argument** — the six
ranked items (slides 1–6). They are real products, correctly shown, and they
must stay recognisable as cheap beauty buys, but **no single one of them
needs to be identity-preserved.** Swap the MUA highlighter for another
budget highlighter and the advert still works. Swap the lash serum and it
does not.

This is a category the system currently has no way to express: *"a real
product that matters as a class, not as an identity."*

## 6. Which product should ultimately be substituted

**The "glow for it" lash growth serum on slide 7.** That is the one being
sold, and the only one whose exact identity — pink metallic tube, black cap,
vertical lowercase lettering — must survive a recreation.

**The system has no idea.** It assigned all seven slides to "Security Check"
with `prominence = primary`. Its Product Lock Profile therefore describes a
bot-block page, and the reference library it built for identity preservation
contains 25 images of nothing relevant.

A correct system would have: one identity-locked product (slide 7), six
class-level items (slides 1–6), and a set of freely replaceable props.

## 7. Repeated visual elements — stylistic vs narrative

**Stylistic repetition** (a consistent look; safe to reinterpret as long as
it stays consistent):
- one product, upright, centred, alone on a plain surface
- soft natural daylight, shallow depth of field, neutral palette
- outlined caption text, small, near the top
- iPhone-shot amateur feel — deliberately not studio

**Narrative repetition** (carries meaning; changing it breaks the advert):
- **the number itself, and its direction.** `1. → 2. → … → 7!!` is the spine.
  It is not decoration. Renumber, reorder, or drop one and the countdown
  collapses.
- **the escalation in the numbers' punctuation.** "5.😭" and "7!! 🥺" are
  rising emotional stakes, not typos.
- **one product per slide.** The format's honesty depends on it — two
  products on a slide would break the ranking.
- **the CTA appearing exactly once, on slide 7.** Its scarcity is what makes
  it land.

The surfaces change between slides (oak on 0, marble and curtain on 7). That
variation is stylistic and harmless. The numbers are not.

## 8. What must persist from one slide to the next

In priority order:

1. **The £20 constraint.** Stated once, on slide 0, and it silently prices
   every later slide. Without it slide 4 is just a brush.
2. **The ranking counter and its direction.** Each slide must know its own
   number and that 7 is the last.
3. **The implicit claim** that everything shown came out of that same £20.
4. **Which slide is the payoff**, so the CTA and urgency land there and
   nowhere else.
5. **The caption treatment**, consistently, so the eight images read as one
   set rather than eight unrelated photos.
6. **The "amateur, honest, iPhone" register.** Making any one slide look like
   a studio ad would undermine the thrift claim the whole thing rests on.

Of these, the system currently stores only #4, via `beat`, and even that
never reaches a slide's compiled prompt. Items 1, 2, 3 and 6 exist nowhere in
the artefacts.

---

## Summary of the gap

| Capability | State |
|---|---|
| Overall purpose | **Understood** — arc summary is accurate |
| Story shape | **Understood** — hook / story ×6 / cta correct on all 8 |
| Per-slide role | **Understood** — stored as `beat` |
| Promoted vs incidental product | **Absent.** All 7 slides assigned to one phantom product |
| Identity-lock target | **Wrong.** Locked onto a bot-block page |
| Cross-slide state (£20, counter) | **Absent** from every artefact |
| Beat reaching the prompt | **No.** Computed, stored, discarded |

The system reads the advert better than the recreations suggest. What it
cannot yet do is **act** on that reading: the narrative understanding never
becomes a constraint, and the product layer is not merely imprecise but
pointed at the wrong object entirely.
