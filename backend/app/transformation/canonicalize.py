"""
Text canonicalisation + confidence gating (point 2).

Raw OCR must never become an exact generation requirement unresolved. This
module:
  - cleans obvious OCR noise deterministically (and reports whether it did);
  - extracts exact commercial values (prices, discounts) as atomic facts;
  - classifies each block into a text_status:
        trusted_exact | exact_commercial_value | meaning_preserve | uncertain
The rule: if noise remains unresolved, the block is `uncertain` and the
pre-validator will refuse to let it be a required exact requirement.
"""
from __future__ import annotations

import re
import unicodedata


def _is_noise_char(ch: str) -> bool:
    cp = ord(ch)
    # Hangul Jamo / Syllables, CJK, private use, controls — not expected in UK creator copy
    if 0x1100 <= cp <= 0x11FF or 0xAC00 <= cp <= 0xD7A3 or 0x4E00 <= cp <= 0x9FFF:
        return True
    if 0xE000 <= cp <= 0xF8FF:            # private use
        return True
    if unicodedata.category(ch) in ("Cc", "Cf", "Co", "Cn") and ch not in ("‍", "️"):
        return True
    return False


_UI_GLYPHS = {"ⓘ"}  # ⓘ info marker and similar enclosed alphanumerics used as UI chrome


def clean_ocr(text: str) -> tuple[str, bool, bool]:
    """Return (cleaned, had_noise, residue_suspicious)."""
    had_noise = False
    # strip UI glyphs
    for g in _UI_GLYPHS:
        if g in text:
            text = text.replace(g, " ")
            had_noise = True
    tokens = text.split()
    kept = []
    for i, tok in enumerate(tokens):
        noise = sum(_is_noise_char(c) for c in tok)
        ratio = noise / max(len(tok), 1)
        # drop tokens that are mostly noise (typical of trailing OCR garbage like "ᄀ0")
        if ratio >= 0.3:
            had_noise = True
            continue
        kept.append(tok)
    cleaned = " ".join(kept).strip()
    residue_suspicious = any(_is_noise_char(c) for c in cleaned)
    return cleaned, had_noise, residue_suspicious


_PRICE_RE = re.compile(r"£\s?\d+(?:\.\d{1,2})?")
_DISC_RE = re.compile(r"-?\d{1,3}\s?%")
_FROM_RE = re.compile(r"[Ff]rom\s*£\s?\d+(?:\.\d{1,2})?")


def extract_commercial_values(text: str) -> list[dict]:
    values: list[dict] = []
    has_pound = "£" in text
    ctx = any(w in text.lower() for w in ("off", "sale", "save", "discount", "was", "now"))
    for m in _DISC_RE.findall(text):
        tok = m.strip()
        num = int("".join(ch for ch in tok if ch.isdigit()) or "0")
        # a % is a discount only in a discount context — "100% dairy free" is NOT a discount
        is_discount = tok.startswith("-") or ((has_pound or ctx) and num <= 95)
        if is_discount:
            values.append({"type": "discount_pct", "value": tok.replace(" ", ""), "raw": m})
    from_prices = {m.split("£")[-1].strip() for m in _FROM_RE.findall(text)}
    for m in _PRICE_RE.findall(text):
        num = m.split("£")[-1].strip()
        vtype = "price_final" if num in from_prices else "price"
        values.append({"type": vtype, "value": "£" + num, "raw": m})
    return values


def classify_text(*, role: str, surface: str, is_primary_hook: bool,
                  cleaned: str, had_noise: bool, residue_suspicious: bool,
                  commercial_values: list[dict]) -> tuple[str, list[str]]:
    """Return (text_status, notes)."""
    notes: list[str] = []
    if had_noise:
        notes.append("ocr noise removed")
    if commercial_values:
        if residue_suspicious:
            return "uncertain", notes + ["commercial block has unresolved noise"]
        return "exact_commercial_value", notes
    if is_primary_hook:
        if residue_suspicious:
            return "uncertain", notes + ["hook wording not confidently clean"]
        return "trusted_exact", notes
    # all other creator copy defaults to meaning-preserve (casual continuations, subheads, packaging)
    return "meaning_preserve", notes
