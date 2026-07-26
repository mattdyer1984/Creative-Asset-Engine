# Provider drift history

**Finding: this is not drift. It is an incomplete migration that new stages
kept inheriting.** No commit silently moved work from Gemini to OpenAI.

## Timeline, from `git log`

| Commit | Date | Effect |
|---|---|---|
| `d1e173f` | initial | `vision_analysis: openai` set as the default. **Gemini was never the default for vision analysis** |
| `ecb4217` | 2026-07-24 | *"Move OCR, Product Lock Profile, Creative Fingerprint to Gemini"* — OCR default flipped to Gemini; `GeminiVisionAnalysisAdapter` added but **deliberately not made the default** |
| `6b57a48` | — | image-generation fallback to GPT Image added |
| `d3d4efa` | — | fallback extended to OCR and the Gemini vision override |

## What `ecb4217` actually decided

Its own comment in `backend/providers.yaml` states the scope explicitly:

> *"vision_analysis deliberately stays `openai` as the DEFAULT — Product Lock
> Profile Stage and Creative Fingerprint Stage explicitly request
> `provider_name="gemini"` per-call … A narrower scope the user chose
> explicitly, to avoid re-calibrating the whole quality bar those tasks judge
> against at the same time as the pipeline stages feeding it change."*

So the partial migration was intentional and reasoned. Two stages were moved
by per-call override; the default was left alone on purpose.

## How the balance then tilted

Because the *default* stayed OpenAI, every stage built afterwards inherited
it without anyone re-deciding:

| Stage | Added | Provider | Why |
|---|---|---|---|
| `scene_intelligence` | `41c81db` 2026-07-23 | OpenAI | called `vision()` with no override |
| `composition_contract` | `a418b2f` 2026-07-26 | OpenAI | same — added by me in Package E |
| `creative_profile` | `0edbd53` 2026-07-26 | OpenAI | same — added by me in Package E |

Those three are now among the most expensive calls in a run.
`scene_intelligence` and `composition_contract` alone were **$0.145 of the
$0.58** analysis cost in the P1 case-02 run.

## Answers to the specific questions asked

- **Last revision where Gemini handled the intended stages:** never. Gemini
  has only ever handled OCR, Creative Fingerprint and Product Lock Profile.
- **Commits that changed routing:** `ecb4217` (the only routing move), plus
  `6b57a48` / `d3d4efa` for fallbacks.
- **Deliberate?** Yes, and documented in-line.
- **Did tests normalise OpenAI as the default?** No. `tests/fakes.py` fakes
  the registry wholesale; it does not encode a provider preference.
- **Does benchmark code differ from production routing?** No. The harness
  calls `SLIDESHOW_STAGE_PIPELINE` and the real registry.
- **Does missing Gemini config cause silent OpenAI fallback?** **Yes, in two
  places**, and this is a real defect:
  - `registry.vision_fallback()` returns the OpenAI default whenever a Gemini
    vision call raises — silently.
  - `generation_engine._generate` falls back to GPT Image on **any**
    exception, with no retry.

## Structural blocker

Three capabilities have **no Gemini adapter at all**, so their routing cannot
be changed by configuration:

```
PRODUCT_ISOLATION_ADAPTERS = {"openai": ...}
TEXT_GENERATION_ADAPTERS   = {"openai": ...}
PROMPT_GENERATION_ADAPTERS = {"openai": ...}
```

Moving product isolation to Gemini — which the intended architecture asks for
— requires writing an adapter, not editing a config key.
