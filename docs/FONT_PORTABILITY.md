# Font portability

**Status: mechanism complete (P2). Font assets not yet installed.**

The resolution mechanism, the configurable font root, the deployment gate and
the pinned-checksum installer are all in place and tested. What remains is
acquiring the twelve redistributable files, which needs network access this
environment does not have.

The typographic renderer (ADR 0001 WP-1.4) resolves a **logical token**, never
a host font by name. `Georgia` existing is an accident of this machine;
`serif_editorial_regular` is a design intent that survives a move to Linux or
a container. That indirection is already in place — this document records what
the tokens currently bind to, and what has to happen before deployment.

## How resolution works now

`resolve_token` tries, in order:

1. **The bundled face** — `font_root() / VENDORED_FACES[token]`.
   `font_root()` is `backend/assets/fonts` unless `CAE_FONT_ROOT` overrides
   it, so a deployment can supply licensed brand faces without a code change.
2. **A host face** — the macOS candidates below, a development convenience
   only.
3. **Failure**, naming the token, the bundled filename it looked for, the
   directory, the host candidates tried, and what to run.

The order is deliberate. If host fonts won, a developer's Mac would silently
produce different output from production — the portability problem restated
rather than solved.

`assert_fonts_are_portable()` is the deployment gate: it **refuses to start**
if any token resolves only to a host face, because output that depends on
which machine drew it makes benchmark scores incomparable across machines.
`font_source(token)` reports `vendored` / `host` / `missing` per token.

## Installing the faces

    python scripts/fetch_fonts.py            # install
    python scripts/fetch_fonts.py --verify   # check what is present
    python scripts/fetch_fonts.py --record   # print digests to pin

Every face is pinned by SHA-256. **A font with a blank pin is refused, not
installed** — a font fetched without a checksum is an unverified binary being
loaded into the renderer. A test asserts nothing is committed unpinned.

The twelve mapped faces are SIL OFL 1.1 or Apache-2.0: Source Serif 4
(regular/italic/bold), Inter (regular/bold), Poppins (regular/bold), Oswald
(regular/bold), Roboto Slab, Dancing Script, Anton.

**Remaining work:** run the installer somewhere with network access, record
the digests, and commit the pins. Until then `assert_fonts_are_portable()`
correctly refuses, and rendering still works on macOS via host fonts.

## Current host bindings (development only)

Every one of these is a macOS system face. **None of them exists on a stock
Linux container**, so today's renderer would fail there — loudly, which is the
intended behaviour.

| Token | Face | Path |
|---|---|---|
| `serif_editorial_regular` | Georgia | `/System/Library/Fonts/Supplemental/Georgia.ttf` |
| `serif_editorial_italic` | Georgia Italic | `/System/Library/Fonts/Supplemental/Georgia Italic.ttf` |
| `serif_editorial_bold` | Georgia Bold | `/System/Library/Fonts/Supplemental/Georgia Bold.ttf` |
| `grotesque_regular` | Helvetica Neue | `/System/Library/Fonts/HelveticaNeue.ttc` |
| `grotesque_bold` | Helvetica Neue Bold | `/System/Library/Fonts/HelveticaNeue.ttc` [1] |
| `geometric_sans_regular` | Avenir Next | `/System/Library/Fonts/Avenir Next.ttc` |
| `geometric_sans_bold` | Avenir Next Bold | `/System/Library/Fonts/Avenir Next.ttc` [1] |
| `condensed_display_regular` | Avenir Next Condensed | `/System/Library/Fonts/Avenir Next Condensed.ttc` |
| `condensed_display_bold` | Avenir Next Condensed Bold | `/System/Library/Fonts/Avenir Next Condensed.ttc` [1] |
| `slab_regular` | Georgia | *(shares the serif face — no true slab available)* |
| `script_regular` | Snell Roundhand | `/System/Library/Fonts/Supplemental/SnellRoundhand.ttc` |
| `display_regular` | Impact | `/System/Library/Fonts/Supplemental/Impact.ttf` |

Fallback candidates (Palatino, Times, Helvetica, Avenir) are equally macOS-only.

## Behaviour when a token cannot be resolved

`resolve_token` raises `UnavailableFontToken` naming the token, the candidates
tried, and this document. **It never substitutes.**

That is deliberate and worth defending: a serif silently rendered in bold
Helvetica is precisely the defect this subsystem was built to remove, and it
is invisible in logs. A loud failure is recoverable; a silent substitution
ships to a customer.

`font_availability()` reports every token's status and is intended for a
startup check once the renderer is wired into the live pipeline (WP-1.5A).

## Proposed deployment-safe approach

Ordered by preference.

**1. Vendor a small open-licence set into the repository.** Four to six
families under SIL OFL or Apache-2.0, committed under `backend/assets/fonts/`
and resolved by relative path. Roughly 2–4 MB. Candidates worth evaluating:

| Token family | Candidate | Licence |
|---|---|---|
| serif editorial | Source Serif 4, EB Garamond, Libre Baskerville | OFL |
| grotesque | Inter, Roboto | OFL / Apache-2.0 |
| geometric sans | Poppins, Montserrat | OFL |
| condensed display | Oswald, Archivo Narrow | OFL |
| slab | Roboto Slab, Zilla Slab | OFL / Apache-2.0 |
| script | Great Vibes, Dancing Script | OFL |

This removes the host dependency entirely, makes rendering reproducible across
machines, and keeps the benchmark harness meaningful — a benchmark scored
against fonts that differ per machine is not a benchmark.

**2. A font package installed at image build time** (`fonts-liberation`,
`fonts-dejavu`). Smaller repository, but reintroduces an environment
dependency and weakens reproducibility.

**3. Configurable font root** via settings, defaulting to the vendored set, so
a deployment can supply licensed brand faces without a code change.

I would do **1 and 3 together**: vendored defaults for reproducibility, with an
override path for anyone who has licensed the real thing.

## What this does not need to solve

Exact face matching. ADR §10.2 settled that: benchmark 4 in any competent
serif beats benchmark 4 in bold Helvetica, and benchmarks 6 and 7 changed
typeface family outright while keeping their hierarchy intact. Effort belongs
in hierarchy, spacing, emphasis and alignment.

## Sequencing

Not required for WP-1.1 (persistence stores a *family class*, not a face) and
not required for WP-1.5A (local validation). It **is** required before any
deployment, and before benchmark scores from different machines are compared.
