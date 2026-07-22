"""backfill slideshows slides product_appearances

Revision ID: 8a76d08b06fe
Revises: d24ebb8f1926
Create Date: 2026-07-22 05:49:20.924991

Phase 2.2 of the Slideshow/Slide migration. Delegates to
app.services.slideshow_backfill.backfill_slideshows (unit-tested
separately in tests/test_slideshow_backfill.py) rather than embedding
the logic here, since Alembic revision filenames aren't cleanly
importable for direct testing. Idempotent - see that module's docstring.

Still purely additive from the running app's point of view:
Creative/CreativeBlueprint remain untouched and authoritative; nothing
reads the newly-populated tables until Phase 2.4 onward.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.services.slideshow_backfill import backfill_slideshows

# revision identifiers, used by Alembic.
revision: str = '8a76d08b06fe'
down_revision: Union[str, None] = 'd24ebb8f1926'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    session = Session(bind=op.get_bind())
    backfill_slideshows(session)


def downgrade() -> None:
    bind = op.get_bind()
    # FK-safe order: children before parents.
    bind.execute(sa.text("DELETE FROM product_appearances"))
    bind.execute(sa.text("DELETE FROM slides"))
    bind.execute(sa.text("DELETE FROM slideshows"))
