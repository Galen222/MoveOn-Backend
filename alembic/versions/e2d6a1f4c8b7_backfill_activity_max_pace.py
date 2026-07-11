"""backfill activity max pace

Revision ID: e2d6a1f4c8b7
Revises: 7c4e2f9a1b6d
Create Date: 2026-07-11
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e2d6a1f4c8b7"
down_revision: Union[str, Sequence[str], None] = "7c4e2f9a1b6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rellena rutas antiguas cuyo ritmo máximo quedó a cero."""
    op.execute(
        """
        UPDATE actividades
        SET ritmo_maximo = LEAST(
            1800,
            GREATEST(
                60,
                CASE
                    WHEN tipo = 'Correr' THEN GREATEST(
                        ROUND(ritmo_medio_movimiento * 0.72)::integer,
                        ritmo_medio_movimiento - 60,
                        LEAST(
                            ROUND(360000.0 / velocidad_max_x100)::integer,
                            GREATEST(1, ritmo_medio_movimiento - 15)
                        )
                    )
                    ELSE GREATEST(
                        ROUND(ritmo_medio_movimiento * 0.80)::integer,
                        ritmo_medio_movimiento - 90,
                        LEAST(
                            ROUND(360000.0 / velocidad_max_x100)::integer,
                            GREATEST(1, ritmo_medio_movimiento - 10)
                        )
                    )
                END
            )
        )
        WHERE ritmo_maximo = 0
          AND ritmo_medio_movimiento > 0
          AND velocidad_max_x100 > 0
        """
    )


def downgrade() -> None:
    """No borra valores derivados porque ya son métricas válidas de actividad."""
