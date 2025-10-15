"""rename knowledge_entries to notes and remove summary

Revision ID: 9b56427a72d4
Revises: 7e71f38f2fec
Create Date: 2025-10-15 22:23:53.956767

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '9b56427a72d4'
down_revision = '7e71f38f2fec'
branch_labels = None
depends_on = None


def upgrade():
    # Rename table from knowledge_entries to notes
    op.rename_table('knowledge_entries', 'notes')
    
    # Remove summary column from notes table
    op.drop_column('notes', 'summary')


def downgrade():
    # Add summary column back
    op.add_column('notes',
        sa.Column('summary', sa.String(length=2000), nullable=True)
    )
    
    # Rename table back to knowledge_entries
    op.rename_table('notes', 'knowledge_entries')
