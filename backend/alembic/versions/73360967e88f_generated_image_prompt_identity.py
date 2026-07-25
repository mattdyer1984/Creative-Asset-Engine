"""generated image prompt identity

Phase 1 remediation, WP-3 (completion).

Adds prompt identity to `generated_images`, ALONGSIDE the existing
`prompt_used` text rather than replacing it. Both are kept deliberately:

  * `prompt_used` is the exact text this image was asked for - what you
    read when a specific output looks wrong;
  * `prompt_id` / `prompt_version` / `prompt_content_hash` say which
    prompt DEFINITION produced it - what you group by when comparing
    many images, and what answers "was this generated before or after
    we changed the compiler?"

Neither substitutes for the other. Rendered text alone cannot be
grouped or compared across images (it embeds per-slide data); identity
alone cannot tell you what this particular image was actually asked for.

All three columns are nullable. Every image generated before WP-3 has
no known prompt identity, and back-filling a guess would assert
something untrue about which wording produced it - the same discipline
applied to the legacy_aggregate cost rows.

Revision ID: 73360967e88f
Revises: 79eae7117ad1
Create Date: 2026-07-25 22:35:53.992944

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '73360967e88f'
down_revision: Union[str, None] = '79eae7117ad1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("generated_images") as batch_op:
        batch_op.add_column(sa.Column("prompt_id", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("prompt_version", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("prompt_content_hash", sa.String(64), nullable=True))

    # Grouping images by the prompt definition that produced them is the
    # whole point of these columns, so index the one you group by.
    op.create_index(
        "ix_generated_images_prompt_content_hash",
        "generated_images",
        ["prompt_content_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_generated_images_prompt_content_hash", table_name="generated_images")
    with op.batch_alter_table("generated_images") as batch_op:
        batch_op.drop_column("prompt_content_hash")
        batch_op.drop_column("prompt_version")
        batch_op.drop_column("prompt_id")
