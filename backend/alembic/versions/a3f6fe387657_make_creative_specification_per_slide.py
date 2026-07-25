"""make creative specification per-slide

Revision ID: a3f6fe387657
Revises: 75c0ba1ec9fc
Create Date: 2026-07-25 09:47:53.455061

Real-world-diagnosed fix (Generate All, see MIGRATION_PLAN.md): a real
Generate All run showed slide 2's generated image was built from
slide 1's own scene - CreativeSpecification was one row per Slideshow,
always built from the *primary* slide's own Creative Fingerprint, so
every slide's generation silently shared the primary slide's spec
regardless of which slide's image was actually being produced.

Adds creative_specifications.slide_id (mirroring creative_fingerprints.
slide_id exactly) and slides.current_creative_specification_id (same
plain-string-pointer convention as slides.current_creative_fingerprint_id
- no FK constraint), and drops slideshows.current_creative_specification_id
(superseded - a slideshow-level "the" spec is meaningless once every
slide has its own). Backfilled, not dropped-and-recreated - every
historical row's true owning slide is exactly recoverable via its own
creative_fingerprint_id -> creative_fingerprints.slide_id (same trick
Phase 2.3 used), so no data is lost.

Batch mode required throughout: SQLite can't ALTER a column's
nullability, add a column with a new FK constraint, or drop a column
outside batch mode.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f6fe387657'
down_revision: Union[str, None] = '75c0ba1ec9fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('creative_specifications') as batch_op:
        batch_op.add_column(sa.Column('slide_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_creative_specifications_slide_id_slides', 'slides', ['slide_id'], ['id']
        )

    with op.batch_alter_table('slides') as batch_op:
        batch_op.add_column(sa.Column('current_creative_specification_id', sa.String(length=36), nullable=True))

    bind = op.get_bind()

    # Every historical CreativeSpecification's true owning slide is
    # exactly recoverable via its own creative_fingerprint_id -> the
    # Creative Fingerprint's own slide_id (same trick Phase 2.3 used for
    # OCR/Creative Fingerprint's own slide_id backfill).
    bind.execute(sa.text(
        "UPDATE creative_specifications SET slide_id = "
        "(SELECT slide_id FROM creative_fingerprints WHERE creative_fingerprints.id = creative_specifications.creative_fingerprint_id)"
    ))

    # Only ever the former primary slide's own row (is_current was
    # previously scoped one-per-slideshow) - every other slide correctly
    # gets NULL, since it never had a real spec of its own before this
    # fix; it gets one the next time the stage runs.
    bind.execute(sa.text(
        "UPDATE slides SET current_creative_specification_id = "
        "(SELECT id FROM creative_specifications WHERE creative_specifications.slide_id = slides.id "
        "AND creative_specifications.is_current = 1)"
    ))

    with op.batch_alter_table('slideshows') as batch_op:
        batch_op.drop_column('current_creative_specification_id')


def downgrade() -> None:
    with op.batch_alter_table('slideshows') as batch_op:
        batch_op.add_column(sa.Column('current_creative_specification_id', sa.String(length=36), nullable=True))

    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE slideshows SET current_creative_specification_id = "
        "(SELECT cs.id FROM creative_specifications cs "
        "JOIN slides s ON s.id = cs.slide_id "
        "WHERE s.slideshow_id = slideshows.id AND cs.is_current = 1)"
    ))

    with op.batch_alter_table('slides') as batch_op:
        batch_op.drop_column('current_creative_specification_id')

    with op.batch_alter_table('creative_specifications') as batch_op:
        batch_op.drop_constraint('fk_creative_specifications_slide_id_slides', type_='foreignkey')
        batch_op.drop_column('slide_id')
