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
