"""
LOCAL generation + evaluation driver — RUN THIS IN YOUR ENVIRONMENT ONLY.

Why local: the Nano Banana key lives in your macOS Keychain
(keyring 'creative-asset-engine' / 'nano_banana_api_key') and the product
reference images live on your disk. Neither is reachable from the cloud
session, so the paid call must run here.

What it does, per representative slide (Ninja reveal, Cologne comparison,
Posture educational):
  1. rebuilds the SAME provider request + typed RequestManifest as the cloud
     session (imports the identical transformation code — no drift);
  2. resolves each product's reference images from the DB (by reference_id ->
     file_path) and loads them;
  3. makes ONE real generation with the general-purpose Nano Banana tier
     (gemini-3.1-flash-image-preview — the Lite tier is known to fail packaging
     text; see app/ai_providers/nano_banana_adapter.py);
  4. saves the image to ./gen_out/<family>.png;
  5. runs the SAME post-generation evaluation (deterministic now; add a VLM
     scorer for the perceptual criteria).

Usage:
    python run_local_generation.py                 # all three
    python run_local_generation.py ninja           # one family: ninja|cologne|posture
    python run_local_generation.py --dry-run        # build requests only, no spend
"""
import os, sys, sqlite3

from app.transformation.attention import derive_attention
from app.transformation.generation_spec import assemble_generation_spec
from app.transformation.adapters.nano_banana_prompt_adapter import NanoBananaPromptAdapter
from app.transformation import postgen_eval
from run_three_families import ninja, cologne, posture, brief_from_plan, req_to_dict
from app.transformation.generation_request import slide_requirements

DB = os.path.join(os.path.dirname(__file__), "data", "creative_asset_engine.db")
OUTDIR = os.path.join(os.path.dirname(__file__), "gen_out")
MODEL = "gemini-3.1-flash-image-preview"      # general-purpose tier (packaging-text capable)
FAMILIES = {"ninja": ninja, "cologne": cologne, "posture": posture}


def reference_paths(reference_ids):
    """Resolve reference_id -> on-disk file_path from the DB (local paths)."""
    if not reference_ids:
        return []
    c = sqlite3.connect(DB)
    q = "select id, file_path from product_reference_images where id in (%s)" % ",".join("?" * len(reference_ids))
    found = {r[0]: r[1] for r in c.execute(q, list(reference_ids))}
    paths = []
    for rid in reference_ids:
        fp = found.get(rid)
        if fp and os.path.exists(fp):
            paths.append(fp)
        else:
            print(f"    ! reference {rid}: {'file missing at ' + fp if fp else 'not in DB'}")
    return paths


def gen_image(prompt, ref_image_paths, out_path, aspect_ratio):
    """One real Nano Banana call. Confirmed against google-genai==2.14.0.

    aspect_ratio is REQUIRED and flows from the spec's canvas (never hardcoded here)."""
    from google import genai
    from google.genai import types
    from PIL import Image
    import keyring
    key = keyring.get_password("creative-asset-engine", "nano_banana_api_key")
    if not key:
        raise SystemExit("No nano_banana_api_key in keyring 'creative-asset-engine'.")
    client = genai.Client(api_key=key)
    contents = [prompt] + [Image.open(p) for p in ref_image_paths]
    resp = client.models.generate_content(
        model=MODEL, contents=contents,
        config=types.GenerateContentConfig(image_config=types.ImageConfig(aspect_ratio=aspect_ratio)),
    )
    for part in resp.candidates[0].content.parts:
        if getattr(part, "inline_data", None) and part.inline_data.data:
            with open(out_path, "wb") as f:
                f.write(part.inline_data.data)
            return out_path
    raise RuntimeError("No image bytes returned; parts=" + str(resp.candidates[0].content.parts))


def make_vlm_scorer():
    """Optional perceptual scorer using a Gemini vision model. Returns (bool, why)."""
    from google import genai
    from PIL import Image
    import keyring
    key = keyring.get_password("creative-asset-engine", "nano_banana_api_key")
    client = genai.Client(api_key=key)

    def score(question, image_path, refs):
        prompt = (f"{question}\nAnswer strictly as 'YES: <reason>' or 'NO: <reason>' in one line.")
        r = client.models.generate_content(model="gemini-2.5-flash",
                                            contents=[prompt, Image.open(image_path)])
        t = (r.text or "").strip()
        return t.upper().startswith("YES"), t
    return score


def run_family(key, dry_run):
    name, plan, own, idx = FAMILIES[key]()
    attention = derive_attention(plan, brief_from_plan(plan))
    spec = assemble_generation_spec(plan, attention, own)
    slide = next(s for s in spec.slides if s.slide_index == idx)
    out = NanoBananaPromptAdapter().write(slide)

    entry = {
        "family": name, "slide_index": idx,
        "provider_request": out.provider_request,
        "requirements": [req_to_dict(r) for r in slide_requirements(slide)],
        "manifest": {
            "encoded": [f"{e.requirement.id.kind}:{e.requirement.id.ref}" for e in out.manifest.entries if e.status == "encoded"],
            "unsupported": [{"id": f"{e.requirement.id.kind}:{e.requirement.id.ref}", "reason": e.reason}
                            for e in out.manifest.entries if e.status == "unsupported"],
        },
        "overlay_handoff": [{"ref": t.ref, "text": t.text} for t in slide.texts if t.disposition == "overlay_handoff"],
    }

    print("=" * 78); print(name, f"(slide {idx}) — model {MODEL}"); print("=" * 78)
    ref_ids = [r for p in slide.products for r in p.reference_ids]
    refs = reference_paths(ref_ids)
    print(f"  references to attach: {len(refs)}")
    img_path = None
    if not dry_run:
        os.makedirs(OUTDIR, exist_ok=True)
        aspect = slide.canvas.output_aspect if slide.canvas else "3:4"
        img_path = gen_image(out.provider_request, refs, os.path.join(OUTDIR, f"{key}.png"), aspect)
        print(f"  saved: {img_path}")

    scorer = None if dry_run else make_vlm_scorer()
    ev = postgen_eval.evaluate(entry, image_path=img_path, vlm_score=scorer)
    print(postgen_eval.render(ev))
    print(f"  FAILED: {[r.criterion for r in ev.failed] or 'none'}; "
          f"PENDING-VLM: {len(ev.pending)}\n")
    return ev


def main():
    args = [a for a in sys.argv[1:]]
    dry_run = "--dry-run" in args
    keys = [a for a in args if a in FAMILIES] or list(FAMILIES)
    for k in keys:
        run_family(k, dry_run)


if __name__ == "__main__":
    main()
