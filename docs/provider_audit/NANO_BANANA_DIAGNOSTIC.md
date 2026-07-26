# Nano Banana diagnostic

**Verdict: Nano Banana is working.** The P1 `503` was a genuine transient
"high demand" response, not an integration defect. No credential, model,
endpoint, encoding or adapter problem exists.

Run with the production adapter and production credentials, **fallback
disabled**.

| | |
|---|---|
| Provider | `nano_banana` |
| Model | `gemini-3.1-flash-image-preview` |
| SDK | `google-genai` 2.14.0 |
| API | `client.models.generate_content` with `types.GenerateContentConfig(image_config=types.ImageConfig(aspect_ratio=...))` |
| Timeout | `AI_PROVIDER_TIMEOUT_SECONDS * 1000` ms |

## Progressive tests

| # | Layer | Result | Latency | Output |
|---|---|---|---|---|
| 1 | text-only generation | **OK** | 46,519 ms | 544,235 bytes |
| 2 | one reference image | **OK** | 7,562 ms | 542,842 bytes |
| 3 | multiple reference images | **OK** | 59,515 ms | 652,015 bytes |
| 4 | compiled production prompt | **OK** | — | covered by test 5 |
| 5 | through the application stage | **OK** | 24,119 ms | P1 case-02 run produced a Nano Banana candidate |

No layer failed, so no diagnosis of a failing layer was required.

## Ruling out each candidate cause

| Cause | Ruled out by |
|---|---|
| credentials | tests 1–3 authenticated and returned images |
| wrong model name | the configured model returned `model=gemini-3.1-flash-image-preview` |
| wrong endpoint / API version | `generate_content` succeeded on SDK 2.14.0 |
| unsupported parameters | `aspect_ratio` accepted at both `1:1` and `3:4` |
| image encoding / MIME | PNG references accepted, single and multiple |
| reference payload | 1 and 3 references both accepted |
| prompt size | production compiled prompt succeeded in the P1 run |
| rate limits | no 429 observed |
| timeout | slowest call 59.5 s, well inside the configured timeout |
| regional config, safety settings | no such error returned |
| adapter code / exception translation | the adapter returned a valid `GeneratedImageResult` |

## Observations worth carrying forward

1. **Latency is highly variable** — 7.6 s to 59.5 s for the same model on
   comparable requests. Any timeout or retry budget must accommodate ~60 s.
2. **The single observed 503 said "high demand … usually temporary"**, which
   is textbook transient and exactly the case for bounded retry with backoff.
3. **Nano Banana output was unpriced** in every run. `nano_banana /
   gemini-3.1-flash-image-preview` has no rate in `pricing.yaml`, so any run
   using it reports incomplete cost.

## Consequence for routing

The fallback fired on a transient error that a single retry would very likely
have absorbed, and sent the work to GPT Image at **$0.25 and 139.9 s** —
against Nano Banana's 24.1 s on the call that succeeded. GPT Image was
behaving as the effective default, exactly as suspected.

---

# Addendum — why 503s arrive while Google's status page is green

Your question was the right one, and it has an answer.

## The 503 is real, and it is model-specific

The P1 traceback shows the `google-genai` SDK's own internal retry (tenacity)
exhausting and re-raising the server's `ServerError`. So this was a genuine
503 from Google after the SDK had already retried — not a client timeout and
not our error translation.

But it was on **`gemini-3.1-flash-image-preview`**. Preview-tier capacity is
managed separately from GA services and is not represented on the status
dashboard. **A green status page and 503s on a preview model are entirely
consistent** — preview capacity is shed under load precisely so GA is not.

## Two hypotheses tested and eliminated

| Hypothesis | Test | Result |
|---|---|---|
| Concurrency triggers it | 3 sequential vs 3 concurrent, identical prompt | **6/6 OK**, 6–11 s. Not concurrency |
| Payload size triggers it | 1, 3, 5, 8 references at 900×1200 with a long prompt | **4/4 OK** — but latency 9.4 s → 172.1 s |

## The signal is latency variance, not failure

Measured on `gemini-3.1-flash-image-preview` for comparable production-sized
work: **14.6 s · 24.1 s · 46.5 s · 59.5 s · 141.2 s · 172.1 s**, against a
**180 s** client timeout. A 12× swing on the same payload shape is
server-side queueing, and 172.1 s leaves 8 s of headroom.

Head-to-head on an identical 8-reference payload:

| Model | Latency |
|---|---|
| `gemini-3.1-flash-lite-image` | **4.6 s** |
| `gemini-3.1-flash-image-preview` | 14.6 s |

## Correction applied

`providers.yaml` moves the primary from the preview tier to
**`gemini-3.1-flash-lite-image`** — the tier Phase 10.2 originally
live-verified, and the adapter's own default. The preview model becomes the
**high-quality escalation rung**, tried after retries and before the
emergency GPT Image fallback.

    primary       nano_banana / gemini-3.1-flash-lite-image
    high quality  nano_banana / gemini-3.1-flash-image-preview
    fallback      openai      / gpt-image-1

Both Google models remain **explicitly unpriced** in `pricing.yaml`. The
published page does not separate the Lite tier, so no figure can be
attributed with confidence, and no rate has been guessed.
