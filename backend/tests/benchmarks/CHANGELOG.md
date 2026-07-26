# Benchmark suite changelog

Governed by `docs/BENCHMARK_GOVERNANCE.md`. Every entry records what changed,
the evidence, who approved it, and the measured effect on scores.

Scores are comparable only within a suite version. Report them as
`metric @ suite vN`.

---

## v1 — 2026-07-26

The eight gold-standard human recreations, as authored during Package B and
refined through Package C.

**Known open questions, both raised by evidence and NOT yet changed:**

| Case | Field | Current | Evidence | Status |
|---|---|---|---|---|
| `case01_weather_tv` | zone bounds | tv-screen `[0.08, 0.15, 0.92, 0.36]`, caption y `0.090-0.150` | Pixel measurement: screen occupies y `0.239-0.559`, caption plate y `0.136-0.200`. The inferred contract was accurate to ~0.015; the annotation is wrong by up to 0.20 | Awaiting sign-off |
| `case06_meal_prep` | `typography_system.primary_family` | `serif` | The type is unmistakably a bold sans; inference said `grotesque` | Awaiting sign-off |

Both were authored by eye rather than measured. Neither has been edited:
under the standing rule a fixture is never changed because a score would
improve, and both changes would improve scores.

Recorded scores against this version are in `docs/phase_f/` and
`docs/OPTIMISATION_REPORT.md`.
