# Benchmark library

**These are the specification, not a test suite.** Each case is a human
recreation produced with Nano Banana, paired with its original, and annotated
with the creative reasoning behind it. A case does not merely record whether we
passed — it records how a skilled human recreated the slide, so the engine can
be built toward that and measured against it.

See `docs/adr/0001-creative-intelligence-engine.md` (§16 for this schema, §3 for
what the set as a whole demonstrates).

## Layout

```
case NN _ short_name/
  original.jpg        the source slide
  recreation.jpg      the human recreation — the quality target
  ground_truth.yaml   annotation (schema.yaml)
```

## Why annotation quality matters more than code

Every later work package is scored against these annotations. An annotation
that is vague or wrong will make a correct implementation look like a failure,
or worse, make an incorrect one look like a success. The validation criterion
for WP-0.1 is deliberately about the *schema*: two people must be able to
annotate the same case independently and produce the same structure, with no
free-text escape hatch absorbing the disagreement.

## Fields that carry the most weight

- `text_blocks[].class` and `expected_handling_mechanism` — the baked-in versus
  overlay product rule (ADR §4). Getting these wrong is what stripped designed
  typography and replaced it with a generic caption style.
- `required_invariants` / `forbidden_transformations` — the difference between
  a recreation and a different creative.
- `known_ambiguity` — where the human's intent genuinely cannot be inferred
  from the images alone. Recording it prevents a later reviewer "fixing" an
  annotation that was honestly uncertain.

## Set-level findings (see ADR §3)

- Text wording preserved verbatim in **8/8**.
- The set splits cleanly into **4 designed-editorial** and **4 UGC-caption**
  projects. No pair mixes designed typography with a platform caption.
- Human identity changes in **5/5** pairs containing people; pose and framing
  survive.
- Composition is **not** preserved — camera moves (2, 8), panels reorder (5).
- Production value is deliberately raised in **2/8** (cases 2 and 6).
