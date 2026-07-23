"""create listings, product_bundles, product_bundle_members tables and add listing_id to product_source_imports

Revision ID: d3bafd6a4965
Revises: 37e53bed7ec8
Create Date: 2026-07-22 19:31:22.601693

Phase 5.8 of the catalogue layer (see MIGRATION_PLAN.md's frozen
catalogue ADR). Additive only:

- New listings table (Listing) - one marketplace's specific sellable
  page: commercial facts (price, seller, rating, units sold, shipping)
  plus a resolution pointer (resolved_product_id / resolved_bundle_id,
  exactly one set once resolved) to what it represents.
- New product_bundles table (ProductBundle) - declares that N Products
  are sold together as one unit. Pure composition, no attribute data of
  its own.
- New product_bundle_members table (ProductBundleMember) - join: which
  Products, and how many of each, compose a ProductBundle.
- product_source_imports gains a new, nullable listing_id FK, additive
  alongside the existing product_id - the already-shipped single-product
  import flow (Phase 5.6) is completely unaffected; only the new,
  not-yet-built Listing-aware import path (Phase 5.10+) will ever
  populate it.
- product_source_imports.product_id relaxes from NOT NULL to nullable -
  a Listing-scoped import (Phase 5.10) is created before it's known which
  Product it represents (per the ADR, that resolution is never
  automatic); product_id gets backfilled once a human resolves it. Safe:
  it only permits null, every row the existing direct-import flow writes
  still always supplies product_id immediately.

Batch mode required for the product_source_imports ALTER (SQLite can't
change a column's nullability or add a column with a new FK constraint
outside batch mode) - same as 37e53bed7ec8's product_reference_images
ALTER.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3bafd6a4965'
down_revision: Union[str, None] = '37e53bed7ec8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'product_bundles',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=True),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'listings',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('source_type', sa.String(length=64), nullable=False),
        sa.Column('source_url', sa.String(length=2048), nullable=False),
        sa.Column('resolved_product_id', sa.String(length=36), nullable=True),
        sa.Column('resolved_bundle_id', sa.String(length=36), nullable=True),
        sa.Column('price_amount', sa.Float(), nullable=True),
        sa.Column('price_currency', sa.String(length=8), nullable=True),
        sa.Column('seller_name', sa.String(length=255), nullable=True),
        sa.Column('rating', sa.Float(), nullable=True),
        sa.Column('units_sold', sa.Integer(), nullable=True),
        sa.Column('shipping_info', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['resolved_bundle_id'], ['product_bundles.id']),
        sa.ForeignKeyConstraint(['resolved_product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_url'),
    )
    op.create_table(
        'product_bundle_members',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('bundle_id', sa.String(length=36), nullable=False),
        sa.Column('product_id', sa.String(length=36), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['bundle_id'], ['product_bundles.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    with op.batch_alter_table('product_source_imports') as batch_op:
        batch_op.add_column(sa.Column('listing_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_product_source_imports_listing_id', 'listings', ['listing_id'], ['id']
        )
        batch_op.alter_column('product_id', existing_type=sa.String(length=36), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('product_source_imports') as batch_op:
        batch_op.alter_column('product_id', existing_type=sa.String(length=36), nullable=False)
        batch_op.drop_constraint('fk_product_source_imports_listing_id', type_='foreignkey')
        batch_op.drop_column('listing_id')

    op.drop_table('product_bundle_members')
    op.drop_table('listings')
    op.drop_table('product_bundles')
