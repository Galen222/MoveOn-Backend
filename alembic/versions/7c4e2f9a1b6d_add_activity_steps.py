"""add activity steps

Revision ID: 7c4e2f9a1b6d
Revises: b498ff6e4d57
Create Date: 2026-07-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c4e2f9a1b6d"
down_revision: Union[str, Sequence[str], None] = "b498ff6e4d57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Añade pasos como dato opcional para mantener válidas actividades antiguas."""
    op.add_column("actividades", sa.Column("pasos", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_actividades_pasos_range",
        "actividades",
        "pasos IS NULL OR (pasos >= 0 AND pasos <= 500000)",
    )


def downgrade() -> None:
    """Retira la métrica y su restricción."""
    op.drop_constraint(
        "ck_actividades_pasos_range", "actividades", type_="check"
    )
    op.drop_column("actividades", "pasos")
