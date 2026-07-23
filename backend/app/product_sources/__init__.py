"""
Product Source adapters (Phase 5.2 of Product Intelligence, see
MIGRATION_PLAN.md) - the interface every Product Source (a URL: the
generic schema.org/OpenGraph fallback, or a platform-specific adapter
like TikTok Shop) implements, plus the shared normalized evidence model
and canonical field vocabulary every adapter normalizes into.

Mirrors app.ai_providers' shape (a Protocol, a shared response model,
concrete adapters, a registry) more than app.importers' simpler
single-provider-today version - two real adapters exist here from day
one (generic + TikTok Shop), which is what justifies the registry/
Protocol indirection this time (see the "closest existing precedent"
note in MIGRATION_PLAN.md's Phase 5 architecture direction).
"""
