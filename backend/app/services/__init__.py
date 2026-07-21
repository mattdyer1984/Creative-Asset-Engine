"""
Service layer: orchestration logic that sits between the API routers and
the persistence/provider layers. Routers stay thin; anything with actual
decisions in it (which importer to use, how a MarketingCreative becomes
a Creative + CreativeBlueprint) lives here so it's testable without an
HTTP layer.
"""
