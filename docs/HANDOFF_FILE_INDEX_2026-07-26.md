# File index — 2026-07-26 handoff

Why each entry matters. Line references are against HEAD `d8177d7`.

---

## 1. The failure points (read these first)

| Path | Why it matters |
|---|---|
| `backend/app/slideshow_stages/creative_specification_stage.py:163-193` | `_overlay_text` — **verified cause of the blank chat bubbles**. Gates spec copy on OCR `surface == "overlay"` |
| `backend/app/slideshow_stages/creative_specification_stage.py:211` | `depends_on` — excludes narrative. The wiring gap |
| `backend/app/prompts/generation.py` | Four competing text instructions live here: `overlay_inventory`, `no_overlays`, `suppress_overlay_text`, `things_to_avoid` |
| `backend/app/services/platform_affordances.py` | `placement_instruction()` appended unconditionally — the invented pointing hand |
| `backend/app/services/product_source_import.py` | Accepted a TikTok bot-block page as a product ("Security Check") |
| `backend/app/services/quality_engine.py` | Story path accepts on photorealism alone; passed a blank mockup at 0.868 |

## 2. Pipeline and orchestration

| Path | Why |
|---|---|
| `backend/app/slideshow_stages/pipeline.py:48-58` | The actual stage order. Narrative at 57, spec at 58 |
| `backend/app/slideshow_stages/narrative_structure_stage.py` | **Produces correct beats and arc summaries. Nothing downstream of it consumes them for generation** |
| `backend/app/slideshow_stages/orchestrator.py` | Runs the pipeline; wave scheduling |
| `backend/app/slideshow_stages/scheduling.py` | `plan_waves`, dependency validation |
| `backend/app/services/generation_engine.py` | `_route_image_provider`, `_generate_candidates`, three entry points (single / story / bundle) |
| `backend/app/services/decision_engine.py:112` | Sets `plan.provider` unconditionally — broke tier routing until `173edc1` |
| `backend/app/services/prompt_compiler.py` | Turns the spec into a `GenerationRequest` |
| `backend/app/services/tiktok_import_chain.py:125-132` | `normalise_pasted_url` entry point |

## 3. Providers and routing

| Path | Why |
|---|---|
| `backend/providers.yaml` | `routing:` block — the 7 role→provider assignments; `image_generation_high_quality_model` |
| `backend/app/ai_providers/routing.py` | `load_routing()`, raises on unknown/unset role |
| `backend/app/ai_providers/image_routing.py` | Tier selection from ownership + contract. `_get` handles dict vs object |
| `backend/app/ai_providers/failover.py` | Retry / escalation / emergency-fallback separation; `FailoverRecord` |
| `backend/app/ai_providers/registry.py` | `image_generation()`, `image_generation_high_quality()`, `image_generation_fallback()` |
| `backend/app/ai_providers/nano_banana_adapter.py:187-193` | The exact image call — **no seed, no temperature, no safety settings** |

## 4. Analysis artefacts (schemas)

| Path | Why |
|---|---|
| `backend/app/models/ocr_result.py` | `raw_text`, `structured_blocks_json` (`text`, `role`, `surface`) |
| `backend/app/models/narrative_structure.py` | Beats + arc summary — the unused understanding |
| `backend/app/models/composition_contract.py` | `CompositionContractArtifact` — zones, relations |
| `backend/app/models/text_ownership_artifact.py` | `blocks_json`, per-block owner |
| `backend/app/models/product_lock_profile.py` | Identity constraints |
| `backend/app/models/creative_specification.py` | **This becomes the prompt** |
| `backend/app/services/composition_schema.py` | `ZoneRole`, `Relation` closed vocabularies |
| `backend/app/models/_analysis_artifact_mixin.py` | `is_current`, `analysis_run_id`, `schema_version` |

## 5. Prompts

| Path | Why |
|---|---|
| `backend/app/prompts/generation.py` | `GENERATION_COMPILER` (v6.1), `CREATIVE_SPECIFICATION` (v2.0) |
| `backend/app/prompts/analysis.py:24` | The OCR prompt — **defines `physical` as including "a screen"**, the root of C1 |
| `backend/app/prompts/core.py` | Registry, content hashing |
| `backend/app/prompts/prompts.lock` | Version + hash per prompt |
| `backend/tests/snapshots/prompts/` | **No fixture contains an emoji or a screenshot creative** — why the guards missed `8ebe4c6` |

## 6. Security / import

| Path | Why |
|---|---|
| `backend/app/services/safe_fetch.py:79-96` | TikTok allowlist; `vm.tiktok.com` added on evidence, `vt.tiktok.com` deliberately excluded |
| `backend/app/services/safe_fetch.py` | `normalise_pasted_url` — adds `https://`, never upgrades `http://` |
| `backend/app/importers/playwright_tiktok.py` | `_SHORT_URL_RE`, `_resolve_short_url`, `_canonical_post_url`, `_normalize_post_url` |
| `backend/app/routers/slideshows.py:219` | `UnsafeURLError` → 400 (was an unhandled 500) |

## 7. Evidence — the two failed slideshows

| Path / ID | Why |
|---|---|
| `backend/data/creative_asset_engine.db` | **Contains both failures. Preserve.** |
| Slideshow `c9c68661` | Tech bundle, 2 slides. Slide 0 = `b89da4ff-b961-4271-9c91-7419c7f39517` |
| Slideshow `cc1476d5` | £20 haul, 8 slides, all assigned to "Security Check" |
| `backend/data/*.pre-migration-*.db` | 3 backups, pre-`b392e2c34de2` |
| `backend/data/storage/creatives/*/original.jpg` | Source slide images |

## 8. Reports

| Path | Why | Trust |
|---|---|---|
| `docs/HANDOFF_2026-07-26.md` | This handoff | — |
| `docs/forensics/TECH_BUNDLE_FAILURE.md` | Verified failure chain, 13 questions answered | High |
| `docs/forensics/HAUL_SLIDESHOW_READING.md` | Phantom-product finding; narrative reading | High |
| `docs/variance/CASE02_RESULTS.md` | 1/8 ship-ready | High for generation variance; **measures nothing about narrative** |
| `docs/variance/CASE02_PROTOCOL.md` | Pre-registered criteria | High |
| `docs/PROJECT_STATE_2026-07-26.md` | Pre-forensics assessment | **Superseded — its central claim is wrong** |
| `docs/PRODUCTION_CHECKLIST.md` | Deployment steps | **Stale** — understates the gap |
| `docs/BENCHMARK_GOVERNANCE.md` | Suite rules | Current |
| `docs/provider_audit/*` | Routing audit, drift history, Nano Banana diagnostic | Current |
| `docs/phase_f/*` | Phase F reports, P1, tier comparison | Historical |
| `docs/benchmark_review/*` | Two open disputes | Current |

## 9. Benchmarks

| Path | Why |
|---|---|
| `backend/tests/benchmarks/VERSION` | **4** |
| `backend/tests/benchmarks/CHANGELOG.md` | v4 entry documents the cover replacement and its evidence |
| `backend/tests/benchmarks/case02_books/references/MANIFEST.yaml` | Per-asset provenance, licence, `edition_match` |
| `backend/tests/benchmarks/case*/ground_truth.yaml` | 8 gold-standard recreations |

## 10. Tests — and what they do not prove

| Path | Proves | Blind spot |
|---|---|---|
| `backend/tests/test_overlay_text_extraction.py` | `_overlay_text` filters `physical` | **Encodes the defect as expected behaviour** |
| `backend/tests/test_overlay_inventory.py` | Prompt wording | Never that real copy reaches the prompt |
| `backend/tests/test_platform_affordances.py` | Rule stated; CTA placement | Never whether the slide should have a CTA |
| `backend/tests/test_image_routing.py` | Tier logic | Passed while the module had zero effect |
| `backend/tests/test_generation_tier_wiring.py` | Router is reached | Nothing about output quality |
| `backend/tests/test_prompt_registry.py` | Wording unchanged | Fixtures lack emoji and screenshot creatives |
| `backend/tests/test_tiktok_short_links.py` | Import + security boundary | — (sound) |
| `backend/tests/fakes.py` | Shared fakes | Must be updated when adapter signatures change |

## 11. Scripts

| Path | Why |
|---|---|
| `scripts/variance/run_variance.py` | Frozen-config harness. **Bypasses `record_provider_call`** |
| `scripts/variance/prepare_references.py` | Scores references without paying for throwaway images |
| `scripts/phase_f/run_benchmarks.py:275` | Reference loading gated behind `--include-generation` |
| `scripts/migrate.py` | Refuses live DB without `--live`; takes a backup |
| `scripts/spend.py` | `today`, `forecast` — no provider calls |
| `scripts/fetch_fonts.py` | Not yet run — fonts still missing |
| `scripts/release_validation.py` | Real-provider release gate |

## 12. Migrations

| Path | Why |
|---|---|
| `backend/alembic/versions/` | 45 files; head `b392e2c34de2` |
| `b392e2c34de2_validation_status_on_inferred_artifacts.py` | Current head |
| `1f46f688fc71` | Final output render manifest — applied this session |

## 13. Commits

Full detail in `HANDOFF_GIT_TIMELINE_2026-07-26.md`. Quick reference:

| Hash | Summary | Verdict |
|---|---|---|
| `d8177d7` | Haul forensics | HEAD |
| `063d9a5` | Tech-bundle forensics | retain |
| `a93d87f` | Import fixes | retain |
| `dd9f79e` | Frontend missing-step hint | retain |
| `db6af61` | Variance results | retain |
| `05db04f`, `12b890e`, `1e33920` | Variance harness | retain |
| `482862f` | Project state | superseded |
| `f9e3348` | Overlay inventory | **revert-test** |
| `8ebe4c6` | Pointer emoji | review |
| `d613a2a` | Buy-box CTA | review |
| `173edc1` | Tier wiring | retain |
| `2a65c51` | Suite v4 | retain |
| `4a30418` | Session start — **baseline for comparison** | — |
