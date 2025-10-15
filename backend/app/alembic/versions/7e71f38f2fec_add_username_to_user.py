"""add_username_to_user

Revision ID: 7e71f38f2fec
Revises: d9f961e953df
Create Date: 2025-10-15 22:05:17.946140

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '7e71f38f2fec'
down_revision = 'd9f961e953df'
branch_labels = None
depends_on = None


def upgrade():
    # Add username column as nullable first
    op.add_column('user', sa.Column('username', sa.String(), nullable=True))
    
    # Create unique index on username
    op.create_index(op.f('ix_user_username'), 'user', ['username'], unique=True)
    
    # Optionally: populate username from email for existing users
    # This sets username to the part before @ in email
    op.execute("""
        UPDATE "user" 
        SET username = SPLIT_PART(email, '@', 1) 
        WHERE username IS NULL
    """)
    
    # Now make username non-nullable
    op.alter_column('user', 'username', nullable=False)


def downgrade():
    # Drop index and column
    op.drop_index(op.f('ix_user_username'), table_name='user')
    op.drop_column('user', 'username')
