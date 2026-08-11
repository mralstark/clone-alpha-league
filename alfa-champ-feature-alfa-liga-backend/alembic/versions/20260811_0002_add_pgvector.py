"""add pgvector extension and knowledge_base table

Revision ID: 20260811_0002
Revises: 20260809_0001_initial
Create Date: 2026-08-11 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260811_0002'
down_revision = '20260809_0001_initial'
branch_labels = None
def upgrade() -> None:
    # Enable pgvector extension (no-op on DBs that lack it)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.create_table(
        'knowledge_base_entries',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('category', sa.String(), nullable=False, index=True),
        sa.Column('okved', sa.String(), nullable=True, index=True),
        sa.Column('target_metric', sa.String(), nullable=False, index=True),
        sa.Column('seasonality', sa.String(), nullable=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('action_items', sa.JSON(), nullable=False),
        sa.Column('associated_products', sa.JSON(), nullable=False),
        # Use vector type for embeddings in Postgres
        sa.Column('embedding', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Note: creating HNSW index requires pgvector's hnsw operator class; guard in raw SQL
    try:
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_kb_embedding_hnsw ON knowledge_base_entries USING hnsw (embedding vector_cosine_ops);"
        )
    except Exception:
        # If the database doesn't support hnsw, skip index creation; migrations remain portable.
        pass

def downgrade() -> None:
    op.drop_index('idx_kb_embedding_hnsw', table_name='knowledge_base_entries', if_exists=True)
    op.drop_table('knowledge_base_entries')
    try:
        op.execute("DROP EXTENSION IF EXISTS vector;")
    except Exception:
        pass
