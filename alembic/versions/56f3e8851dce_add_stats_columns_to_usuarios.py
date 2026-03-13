"""add_stats_columns_to_usuarios

Revision ID: 56f3e8851dce
Revises: 877311255ecd
Create Date: 2026-03-13 00:00:00.000000

Cambios:
- Añade total_calorias (BigInteger, NOT NULL, default 0)
- Añade objetivo_semanal_metros (BigInteger, NOT NULL, default 50000)
- Añade objetivo_mensual_metros (BigInteger, NOT NULL, default 150000)
- Añade CheckConstraints correspondientes

No se toca ninguna tabla ni columna existente.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '56f3e8851dce'
down_revision: Union[str, Sequence[str], None] = '877311255ecd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('usuarios', sa.Column('total_calorias',
                  sa.BigInteger(), server_default=sa.text('0'), nullable=False))
    op.create_check_constraint(
        'ck_usuarios_total_calorias_non_negative', 'usuarios', 'total_calorias >= 0')

    op.add_column('usuarios', sa.Column('objetivo_semanal_metros',
                  sa.BigInteger(), server_default=sa.text('50000'), nullable=False))
    op.create_check_constraint('ck_usuarios_objetivo_semanal_range',
                               'usuarios', 'objetivo_semanal_metros BETWEEN 10 AND 2000000')

    op.add_column('usuarios', sa.Column('objetivo_mensual_metros',
                  sa.BigInteger(), server_default=sa.text('150000'), nullable=False))
    op.create_check_constraint('ck_usuarios_objetivo_mensual_range',
                               'usuarios', 'objetivo_mensual_metros BETWEEN 10 AND 2000000')


def downgrade() -> None:
    op.drop_constraint('ck_usuarios_objetivo_mensual_range',
                       'usuarios', type_='check')
    op.drop_column('usuarios', 'objetivo_mensual_metros')

    op.drop_constraint('ck_usuarios_objetivo_semanal_range',
                       'usuarios', type_='check')
    op.drop_column('usuarios', 'objetivo_semanal_metros')

    op.drop_constraint(
        'ck_usuarios_total_calorias_non_negative', 'usuarios', type_='check')
    op.drop_column('usuarios', 'total_calorias')
