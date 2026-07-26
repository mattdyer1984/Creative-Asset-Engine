# Canonical Product References — governed benchmark assets

**A Creative Input and a Canonical Product Reference are different assets and
stay separate.**

`original.jpg` is the creative being analysed. It carries overlaid captions,
shelf context, surrounding products, perspective distortion and promotional
graphics. Production never treats such a frame as a product reference, and
the reference-scoring gate correctly rejects one — measured on
`case08_fan_shelf` at 0.4575, with the reason *"Large overlaid caption text
obscures the lower middle of the packaging"*.

`references/` holds what production would actually receive: clean,
product-only imagery. These are governed benchmark resources in exactly the
same way the creatives are.

## Layout

    <case>/
      original.jpg          Creative Input      — the creative being analysed
      recreation.jpg        Creative Input      — the human gold standard
      references/
        MANIFEST.yaml       provenance, licence, checksum for every asset
        <asset>.jpg         Canonical Product Reference

## Manifest

Every asset must be declared. An undeclared file in `references/` fails the
fixture tests, and so does a declared asset whose checksum does not match —
an unverified image reaching the reference library is the same class of
problem as an unverified font reaching the renderer.

```yaml
assets:
  - file: fan-front.jpg
    role: packaging            # packaging | product | detail | angle
    sha256: "<64 hex chars>"
    source: "<where it came from>"
    licence: "<licence, or 'owned' if you shot it>"
    licence_url: "<terms>"
    added_in_suite_version: 3
    notes: "front-on, no caption, no shelf context"
```

## Acceptance criteria

A canonical reference must be:

1. **Product only** — no overlaid caption, no promotional graphic, no price
   label, no surrounding products.
2. **Unoccluded** — nothing crossing the product.
3. **Front-on or a declared angle**, with `role` set accordingly.
4. **Legible branding** where the product carries any, since Product Lock is
   expected to preserve it.
5. **Redistributable**, with the licence recorded. An asset whose licence
   cannot be stated does not go in.

These mirror what reference scoring already checks. The benchmark supplies
inputs production would accept; **it does not relax the gate to get through
it.**

## Status

**No assets yet.** The directories and manifests exist so the mechanism is
testable and so the required assets are unambiguous. Until they are supplied,
the affected cases cannot exercise reference conditioning, image generation,
ownership enforcement, editorial rendering or final validation.
