"""
The new, parallel Slideshow/Slide analysis pipeline (Phase 2.4 of the
Slideshow/Slide migration).

Deliberately a separate package from app.stages, not a modification of
it: every stage here is a from-scratch parallel implementation operating
on Slideshow/Slide instead of Creative/CreativeBlueprint, built and
tested without touching or being reachable from the existing, live
pipeline in app.stages. Nothing in app.routers, app.orchestrator, or
app.stages imports anything from this package, and nothing here imports
from those - see the migration roadmap for why (Phase 2.5 wires this up
to a new API surface; Phase 2.6 cuts the frontend over to it; Phase 2.7
removes app.stages/app.orchestrator/the old routes once this has fully
taken over).
"""
