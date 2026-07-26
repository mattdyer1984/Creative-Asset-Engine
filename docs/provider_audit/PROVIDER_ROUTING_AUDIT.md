# Provider routing audit

**Suite v3 · measured from code and from the P1 case-02 run.**
Companion documents: `PROVIDER_DRIFT_HISTORY.md`, `NANO_BANANA_DIAGNOSTIC.md`.

---

## 1. Headline

| Question | Answer |
|---|---|
| Had routing drifted? | **No — the Gemini migration was deliberately partial and never completed.** New stages inherited the untouched OpenAI default |
| Is Nano Banana working? | **Yes.** All diagnostic layers passed with production credentials |
| Was GPT Image the effective default? | **Yes, in effect.** One transient error sent generation to it, with no retry |
| Was fallback silent? | **Yes, in two places** — image generation and Gemini vision |

## 2. Stage-by-stage map (before correction)

Measured from the 13 provider calls in the P1 case-02 run.

| Stage | Provider | Model | Intended | Hard-coded? | Local-capable? | Cost (run) |
|---|---|---|---|---|---|---|
| OCR | **gemini** | gemini-flash-latest | gemini ✅ | no | no | $0.0075 |
| Creative Fingerprint | **gemini** | gemini-pro-latest | gemini ✅ | `provider_name="gemini"` | no | unpriced |
| Product Lock Profile | **gemini** | gemini-pro-latest | gemini ✅ | `provider_name="gemini"` | no | unpriced |
| Product Isolation | openai | gpt-5.5 | **gemini** ❌ | no Gemini adapter exists | no | $0.0418 |
| Scene Intelligence | openai | gpt-5.5 | **gemini** ❌ | no | no | $0.0607 |
| Composition Contract | openai | gpt-5.5 | **gemini** ❌ | no | no | $0.0840 |
| Creative Profile (typography) | openai | gpt-5.5 | **gemini** ❌ | no | partly — text mode is already local | (not in this run) |
| Text Ownership | **local** | — | local ✅ | — | yes | $0 |
| Marketing Analysis | openai | gpt-5.5 | openai ✅ | no Gemini adapter | no | $0.0119 |
| Narrative Structure | openai | gpt-5.5 | openai ✅ | no Gemini adapter | no | $0.0046 |
| Creative Specification | openai | gpt-5.5 | openai ✅ | no Gemini adapter | no | $0.0385 |
| Reference Scoring | openai | gpt-5.5 | **gemini** ❌ | no | tier-1 checks already local | — |
| Image Generation | nano_banana → **openai** | gpt-image-1 | nano_banana ❌ | no | no | **$0.25** |
| Image Validation ×2 | openai | gpt-5.5 | **gemini** ❌ | no | no | $0.0811 |
| Ownership Enforcement | **local** | — | local ✅ | — | yes | $0 |
| Editorial Rendering | **local** | — | local ✅ | — | yes | $0 |
| Winner Selection | **local** | — | local ✅ | — | yes | $0 |

**9 OpenAI · 3 Gemini · 1 Nano Banana.** Of the $0.58 analysis cost,
`$0.145` was Scene Intelligence + Composition Contract alone.

## 3. Retry and fallback (before)

```python
try:
    result = image_provider.generate_image(request)
except Exception:                       # everything, including our own bugs
    result = fallback_provider.generate_image(request)   # straight to GPT Image
```

- no retry, no backoff, no escalation
- `except Exception` caught auth failures, invalid models, safety refusals
- no record of the fallback on the result

`registry.vision_fallback()` has the same shape for Gemini vision calls.

## 4. What was corrected

**`app/ai_providers/failover.py`** — retry the primary with exponential
backoff for genuinely transient failures only (429/500/502/503/504, or a
message naming a transient condition), escalate to the higher-quality primary
model if configured, and reach the emergency provider only after the primary
path is exhausted. **Non-transient errors raise immediately and unchanged.**
Every attempt is recorded in a `FailoverRecord`: primary provider and model,
attempt count, each transient error, escalation, fallback reason, and the
provider that actually produced the image.

**`app/ai_providers/routing.py`** — role-based routing declared in
`providers.yaml`. Unknown role, unset role or unknown provider **raises**.

    visual_analysis        gemini      structured_reasoning   openai
    primary_image          nano_banana high_quality_image     nano_banana
    fallback_image         openai      visual_validation      gemini
    policy_validation      openai

28 tests cover the failover policy.

## 5. What was NOT changed, and why

**Capability routing is unchanged.** The roles are now declared, but the
adapters each capability uses are as before. Moving them is a behaviour
change to quality-bearing stages and needs measuring against the benchmark,
not asserting — the same reasoning `ecb4217` gave for stopping where it did.

**Three capabilities have no Gemini adapter at all:**

```
PRODUCT_ISOLATION_ADAPTERS = {"openai": ...}
TEXT_GENERATION_ADAPTERS   = {"openai": ...}
PROMPT_GENERATION_ADAPTERS = {"openai": ...}
```

Product Isolation cannot move to Gemini by configuration; it needs an
adapter written.

## 6. Recommended next steps, ranked

| # | Action | Evidence | Risk |
|---|---|---|---|
| 1 | Move **Scene Intelligence** and **Composition Contract** to Gemini | $0.145/run, 25% of analysis cost | low — both already validate their own output |
| 2 | Write a **Gemini product-isolation adapter** | $0.042/run and the intended architecture | medium — new adapter |
| 3 | Move **image validation** to Gemini | $0.081/run | **high — this is the gate that rejected P1.** Move last, and measure accept-rate before and after |
| 4 | Price `gemini-pro-latest` and `gemini-3.1-flash-image-preview` | 3 of 13 calls unpriced | none |

Each should be an A/B against suite v3, not a config edit.

## 7. Unresolved risks

1. **`gemini-pro-latest` and the Nano Banana model are unpriced.** Moving
   more work to Gemini makes cost reporting *less* complete, not more.
2. **Image validation is the quality gate.** Switching the judge while
   candidate quality is still being established would make any change in
   accept rate unattributable.
3. **Nano Banana latency is 7.6–59.5 s.** Retry budgets must accommodate it.
4. **`vision_fallback` remains silent.** Fixed for image generation; the
   vision path still substitutes OpenAI without recording it.
