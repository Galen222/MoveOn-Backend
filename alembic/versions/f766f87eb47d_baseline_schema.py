# alembic/versions/f766f87eb47d_baseline_schema.py

"""baseline_schema

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f766f87eb47d'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Aplica los cambios del esquema."""
    # Gestiona upgrade.
    op.create_table('usuarios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre_usuario', sa.String(length=50), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_encriptada', sa.String(length=255), nullable=False),
    sa.Column('nombre_real', sa.String(length=80), nullable=True),
    sa.Column('fecha_nacimiento', sa.Date(), nullable=False),
    sa.Column('genero', sa.String(length=20), nullable=True),
    sa.Column('altura', sa.Integer(), nullable=True),
    sa.Column('peso', sa.Float(), nullable=True),
    sa.Column('provincia', sa.String(length=40), nullable=True),
    sa.Column('foto_perfil', sa.String(length=500), nullable=True),
    sa.Column('foto_fecha_actualizacion', sa.DateTime(timezone=True), nullable=True),
    sa.Column('total_metros', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('total_calorias', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('total_duracion_segundos', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('total_actividades', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('objetivo_semanal_metros', sa.BigInteger(), server_default=sa.text('50000'), nullable=False),
    sa.Column('objetivo_mensual_metros', sa.BigInteger(), server_default=sa.text('150000'), nullable=False),
    sa.Column('fecha_registro', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('fecha_eula', sa.DateTime(timezone=True), nullable=False),
    sa.Column('acepta_terminos', sa.Boolean(), nullable=False),
    sa.Column('version_terminos', sa.String(length=10), nullable=False),
    sa.Column('perfil_visible', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('codigo_recuperacion', sa.String(length=64), nullable=True),
    sa.Column('codigo_expiracion', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("codigo_recuperacion IS NULL OR codigo_recuperacion ~* '^[0-9a-f]{64}$'", name='ck_usuarios_codigo_recuperacion_hex64'),
    sa.CheckConstraint("email !~ '[[:space:]]'", name='ck_usuarios_email_no_spaces'),
    sa.CheckConstraint("email ~ '^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$'", name='ck_usuarios_email_basic_format'),
    sa.CheckConstraint("fecha_nacimiento <= (CURRENT_DATE - INTERVAL '18 years')", name='ck_usuarios_fecha_nacimiento_adult'),
    sa.CheckConstraint("genero IS NULL OR genero IN ('Hombre', 'Mujer', 'Otro')", name='ck_usuarios_genero_values'),
    sa.CheckConstraint("nombre_usuario ~ '^[A-Za-z0-9]+$'", name='ck_usuarios_nombre_usuario_alnum'),
    sa.CheckConstraint("provincia IS NULL OR provincia IN ('A Coruña', 'Albacete', 'Alicante', 'Almería', 'Asturias', 'Badajoz', 'Barcelona', 'Burgos', 'Cantabria', 'Castellón', 'Ceuta', 'Ciudad Real', 'Cuenca', 'Cáceres', 'Cádiz', 'Córdoba', 'Girona', 'Granada', 'Guadalajara', 'Guipúzcoa', 'Huelva', 'Huesca', 'Islas Baleares', 'Jaén', 'La Rioja', 'Las Palmas', 'León', 'Lleida', 'Lugo', 'Madrid', 'Melilla', 'Murcia', 'Málaga', 'Navarra', 'Ourense', 'Palencia', 'Pontevedra', 'Salamanca', 'Santa Cruz de Tenerife', 'Segovia', 'Sevilla', 'Soria', 'Tarragona', 'Teruel', 'Toledo', 'Valencia', 'Valladolid', 'Vizcaya', 'Zamora', 'Zaragoza', 'Álava', 'Ávila')", name='ck_usuarios_provincia_values'),
    sa.CheckConstraint('(codigo_recuperacion IS NULL) = (codigo_expiracion IS NULL)', name='ck_usuarios_codigo_recuperacion_pair'),
    sa.CheckConstraint('acepta_terminos IS TRUE', name='ck_usuarios_acepta_terminos_true'),
    sa.CheckConstraint('altura IS NULL OR (altura BETWEEN 50 AND 300)', name='ck_usuarios_altura_range'),
    sa.CheckConstraint('char_length(btrim(password_encriptada)) > 0', name='ck_usuarios_password_hash_non_empty'),
    sa.CheckConstraint('char_length(btrim(version_terminos)) BETWEEN 1 AND 10', name='ck_usuarios_version_terminos_len'),
    sa.CheckConstraint('char_length(email) BETWEEN 3 AND 320', name='ck_usuarios_email_len'),
    sa.CheckConstraint('char_length(nombre_usuario) BETWEEN 5 AND 50', name='ck_usuarios_nombre_usuario_len'),
    sa.CheckConstraint('email = lower(btrim(email))', name='ck_usuarios_email_normalized_lower'),
    sa.CheckConstraint('fecha_nacimiento <= CURRENT_DATE', name='ck_usuarios_fecha_nacimiento_not_future'),
    sa.CheckConstraint('foto_perfil IS NULL OR char_length(btrim(foto_perfil)) BETWEEN 1 AND 500', name='ck_usuarios_foto_perfil_len'),
    sa.CheckConstraint('nombre_real IS NULL OR char_length(btrim(nombre_real)) BETWEEN 3 AND 80', name='ck_usuarios_nombre_real_len'),
    sa.CheckConstraint('objetivo_mensual_metros BETWEEN 10 AND 2000000', name='ck_usuarios_objetivo_mensual_range'),
    sa.CheckConstraint('objetivo_semanal_metros BETWEEN 10 AND 2000000', name='ck_usuarios_objetivo_semanal_range'),
    sa.CheckConstraint('peso IS NULL OR (peso BETWEEN 20 AND 300)', name='ck_usuarios_peso_range'),
    sa.CheckConstraint('total_actividades >= 0', name='ck_usuarios_total_actividades_non_negative'),
    sa.CheckConstraint('total_calorias >= 0', name='ck_usuarios_total_calorias_non_negative'),
    sa.CheckConstraint('total_duracion_segundos >= 0', name='ck_usuarios_total_duracion_non_negative'),
    sa.CheckConstraint('total_metros >= 0', name='ck_usuarios_total_metros_non_negative'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_usuarios_total_metros'), 'usuarios', ['total_metros'], unique=False)
    op.create_index('uq_usuarios_email_lower', 'usuarios', [sa.literal_column('lower(email)')], unique=True)
    op.create_index('uq_usuarios_nombre_usuario_lower', 'usuarios', [sa.literal_column('lower(nombre_usuario)')], unique=True)
    op.create_table('actividades',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('distancia', sa.Integer(), nullable=False),
    sa.Column('duracion_total', sa.Integer(), nullable=False),
    sa.Column('duracion_movimiento', sa.Integer(), nullable=False),
    sa.Column('duracion_parado', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('duracion_pausa_manual', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('calorias_quemadas', sa.Integer(), nullable=False),
    sa.Column('ritmo_medio_movimiento', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('ritmo_medio_total', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('ritmo_maximo', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('velocidad_media_x100', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('velocidad_max_x100', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('auto_pausas', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('pausas_manuales', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('alertas_velocidad', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('ruta_polilinea', sa.Text(), nullable=True),
    sa.Column('ruta_mapa_url', sa.String(length=2048), nullable=True),
    sa.Column('fecha_ruta', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.CheckConstraint("ruta_mapa_url IS NULL OR ruta_mapa_url ~* '^https?://'", name='ck_actividades_ruta_mapa_url_http'),
    sa.CheckConstraint("tipo IN ('Caminar', 'Correr')", name='ck_actividades_tipo_values'),
    sa.CheckConstraint('alertas_velocidad >= 0 AND alertas_velocidad <= 500', name='ck_actividades_alertas_velocidad_range'),
    sa.CheckConstraint('auto_pausas >= 0 AND auto_pausas <= 500', name='ck_actividades_auto_pausas_range'),
    sa.CheckConstraint('calorias_quemadas > 0 AND calorias_quemadas <= 10000', name='ck_actividades_calorias_range'),
    sa.CheckConstraint('distancia > 0 AND distancia <= 300000', name='ck_actividades_distancia_range'),
    sa.CheckConstraint('duracion_movimiento + duracion_parado = duracion_total', name='ck_actividades_duracion_breakdown_match'),
    sa.CheckConstraint('duracion_movimiento > 0 AND duracion_movimiento <= 86400', name='ck_actividades_duracion_movimiento_range'),
    sa.CheckConstraint('duracion_parado >= 0 AND duracion_parado <= 86400', name='ck_actividades_duracion_parado_range'),
    sa.CheckConstraint('duracion_pausa_manual <= duracion_total', name='ck_actividades_duracion_pausa_manual_total'),
    sa.CheckConstraint('duracion_pausa_manual >= 0 AND duracion_pausa_manual <= 86400', name='ck_actividades_duracion_pausa_manual_range'),
    sa.CheckConstraint('duracion_total > 0 AND duracion_total <= 86400', name='ck_actividades_duracion_total_range'),
    sa.CheckConstraint('pausas_manuales >= 0 AND pausas_manuales <= 500', name='ck_actividades_pausas_manuales_range'),
    sa.CheckConstraint('ritmo_maximo >= 0 AND ritmo_maximo <= 3600', name='ck_actividades_ritmo_maximo_range'),
    sa.CheckConstraint('ritmo_medio_movimiento >= 0 AND ritmo_medio_movimiento <= 3600', name='ck_actividades_ritmo_medio_movimiento_range'),
    sa.CheckConstraint('ritmo_medio_total >= 0 AND ritmo_medio_total <= 3600', name='ck_actividades_ritmo_medio_total_range'),
    sa.CheckConstraint('ruta_mapa_url IS NULL OR char_length(ruta_mapa_url) <= 2048', name='ck_actividades_ruta_mapa_url_len'),
    sa.CheckConstraint('ruta_polilinea IS NULL OR char_length(ruta_polilinea) >= 5', name='ck_actividades_ruta_polilinea_len'),
    sa.CheckConstraint('velocidad_max_x100 >= 0 AND velocidad_max_x100 <= 10000', name='ck_actividades_velocidad_max_range'),
    sa.CheckConstraint('velocidad_max_x100 >= velocidad_media_x100', name='ck_actividades_velocidad_max_ge_media'),
    sa.CheckConstraint('velocidad_media_x100 >= 0 AND velocidad_media_x100 <= 10000', name='ck_actividades_velocidad_media_range'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_actividades_fecha_ruta'), 'actividades', ['fecha_ruta'], unique=False)
    op.create_index('ix_actividades_usuario_fecha', 'actividades', ['usuario_id', 'fecha_ruta', 'id'], unique=False)
    op.create_index(op.f('ix_actividades_usuario_id'), 'actividades', ['usuario_id'], unique=False)
    op.create_table('sesiones_refresh',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('jti', sa.String(length=64), nullable=False),
    sa.Column('familia_id', sa.String(length=64), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('creada_en', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('ultimo_uso_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expira_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revocada_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reemplazada_por_jti', sa.String(length=64), nullable=True),
    sa.CheckConstraint("token_hash ~* '^[0-9a-f]{64}$'", name='ck_sesiones_refresh_token_hash_hex64'),
    sa.CheckConstraint('char_length(btrim(familia_id)) BETWEEN 1 AND 64', name='ck_sesiones_refresh_familia_non_empty'),
    sa.CheckConstraint('char_length(btrim(jti)) BETWEEN 1 AND 64', name='ck_sesiones_refresh_jti_non_empty'),
    sa.CheckConstraint('expira_en >= creada_en', name='ck_sesiones_refresh_expira_ge_creada'),
    sa.CheckConstraint('reemplazada_por_jti IS NULL OR char_length(btrim(reemplazada_por_jti)) BETWEEN 1 AND 64', name='ck_sesiones_refresh_reemplazada_por_jti_len'),
    sa.CheckConstraint('revocada_en IS NULL OR revocada_en >= creada_en', name='ck_sesiones_refresh_revocada_ge_creada'),
    sa.CheckConstraint('ultimo_uso_en IS NULL OR ultimo_uso_en >= creada_en', name='ck_sesiones_refresh_ultimo_uso_ge_creada'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sesiones_refresh_expira_en'), 'sesiones_refresh', ['expira_en'], unique=False)
    op.create_index(op.f('ix_sesiones_refresh_familia_id'), 'sesiones_refresh', ['familia_id'], unique=False)
    op.create_index(op.f('ix_sesiones_refresh_jti'), 'sesiones_refresh', ['jti'], unique=True)
    op.create_index(op.f('ix_sesiones_refresh_revocada_en'), 'sesiones_refresh', ['revocada_en'], unique=False)
    op.create_index(op.f('ix_sesiones_refresh_usuario_id'), 'sesiones_refresh', ['usuario_id'], unique=False)
    op.create_table('usuarios_auth_social',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('provider_user_id', sa.String(length=255), nullable=False),
    sa.Column('email_social', sa.String(length=320), nullable=True),
    sa.Column('nombre_social', sa.String(length=120), nullable=True),
    sa.Column('avatar_url', sa.String(length=2048), nullable=True),
    sa.Column('creada_en', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('ultimo_login_en', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("avatar_url IS NULL OR avatar_url ~* '^https?://'", name='ck_usuarios_auth_social_avatar_url_http'),
    sa.CheckConstraint("email_social IS NULL OR email_social !~ '[[:space:]]'", name='ck_usuarios_auth_social_email_no_spaces'),
    sa.CheckConstraint("provider IN ('google')", name='ck_usuarios_auth_social_provider_values'),
    sa.CheckConstraint('avatar_url IS NULL OR char_length(avatar_url) <= 2048', name='ck_usuarios_auth_social_avatar_url_len'),
    sa.CheckConstraint('char_length(btrim(provider_user_id)) BETWEEN 1 AND 255', name='ck_usuarios_auth_social_provider_user_id_len'),
    sa.CheckConstraint('email_social IS NULL OR char_length(email_social) BETWEEN 3 AND 320', name='ck_usuarios_auth_social_email_len'),
    sa.CheckConstraint('email_social IS NULL OR email_social = lower(btrim(email_social))', name='ck_usuarios_auth_social_email_normalized_lower'),
    sa.CheckConstraint('nombre_social IS NULL OR char_length(btrim(nombre_social)) BETWEEN 1 AND 120', name='ck_usuarios_auth_social_nombre_social_len'),
    sa.CheckConstraint('ultimo_login_en IS NULL OR ultimo_login_en >= creada_en', name='ck_usuarios_auth_social_ultimo_login_ge_creada'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider', 'provider_user_id', name='uq_usuarios_auth_social_provider_user'),
    sa.UniqueConstraint('usuario_id', 'provider', name='uq_usuarios_auth_social_usuario_provider')
    )
    op.create_index(op.f('ix_usuarios_auth_social_usuario_id'), 'usuarios_auth_social', ['usuario_id'], unique=False)
    op.create_table('actividades_diagnostico',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('actividad_id', sa.Integer(), nullable=True),
    sa.Column('actividad_local_id', sa.String(length=64), nullable=True),
    sa.Column('session_started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('session_finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_timer_tick_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('service_created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('service_destroyed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('elapsed_seconds', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('moving_seconds', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('stopped_seconds', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('manual_pause_seconds', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('distance_meters', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('average_pace_total', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('average_pace_moving', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('max_pace', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('auto_pauses', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('manual_pauses', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('speed_alerts', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('running_classified_seconds', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('walking_classified_seconds', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('service_restart_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('current_status', sa.String(length=40), nullable=True),
    sa.Column('app_version', sa.String(length=64), nullable=True),
    sa.Column('os_version', sa.String(length=64), nullable=True),
    sa.Column('manufacturer', sa.String(length=64), nullable=True),
    sa.Column('model', sa.String(length=128), nullable=True),
    sa.Column('event_log_json', sa.Text(), nullable=True),
    sa.Column('device_info_json', sa.Text(), nullable=True),
    sa.Column('creada_en', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.CheckConstraint('actividad_local_id IS NULL OR char_length(btrim(actividad_local_id)) BETWEEN 1 AND 64', name='ck_act_diag_local_id_len'),
    sa.CheckConstraint('app_version IS NULL OR char_length(btrim(app_version)) <= 64', name='ck_act_diag_app_version_len'),
    sa.CheckConstraint('auto_pauses >= 0', name='ck_act_diag_auto_pauses_non_negative'),
    sa.CheckConstraint('average_pace_moving >= 0', name='ck_act_diag_avg_moving_non_negative'),
    sa.CheckConstraint('average_pace_total >= 0', name='ck_act_diag_avg_total_non_negative'),
    sa.CheckConstraint('current_status IS NULL OR char_length(btrim(current_status)) BETWEEN 1 AND 40', name='ck_act_diag_status_len'),
    sa.CheckConstraint('distance_meters >= 0', name='ck_act_diag_distance_non_negative'),
    sa.CheckConstraint('elapsed_seconds >= 0', name='ck_act_diag_elapsed_non_negative'),
    sa.CheckConstraint('manual_pause_seconds >= 0', name='ck_act_diag_manual_pause_non_negative'),
    sa.CheckConstraint('manual_pauses >= 0', name='ck_act_diag_manual_pauses_non_negative'),
    sa.CheckConstraint('manufacturer IS NULL OR char_length(btrim(manufacturer)) <= 64', name='ck_act_diag_manufacturer_len'),
    sa.CheckConstraint('max_pace >= 0', name='ck_act_diag_max_pace_non_negative'),
    sa.CheckConstraint('model IS NULL OR char_length(btrim(model)) <= 128', name='ck_act_diag_model_len'),
    sa.CheckConstraint('moving_seconds >= 0', name='ck_act_diag_moving_non_negative'),
    sa.CheckConstraint('os_version IS NULL OR char_length(btrim(os_version)) <= 64', name='ck_act_diag_os_version_len'),
    sa.CheckConstraint('running_classified_seconds >= 0', name='ck_act_diag_running_non_negative'),
    sa.CheckConstraint('service_restart_count >= 0', name='ck_act_diag_restart_non_negative'),
    sa.CheckConstraint('speed_alerts >= 0', name='ck_act_diag_speed_alerts_non_negative'),
    sa.CheckConstraint('stopped_seconds >= 0', name='ck_act_diag_stopped_non_negative'),
    sa.CheckConstraint('walking_classified_seconds >= 0', name='ck_act_diag_walking_non_negative'),
    sa.ForeignKeyConstraint(['actividad_id'], ['actividades.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_actividades_diagnostico_actividad_id'), 'actividades_diagnostico', ['actividad_id'], unique=False)
    op.create_index(op.f('ix_actividades_diagnostico_actividad_local_id'), 'actividades_diagnostico', ['actividad_local_id'], unique=False)
    op.create_index(op.f('ix_actividades_diagnostico_creada_en'), 'actividades_diagnostico', ['creada_en'], unique=False)
    op.create_index('ix_actividades_diagnostico_usuario_creada', 'actividades_diagnostico', ['usuario_id', 'creada_en', 'id'], unique=False)
    op.create_index(op.f('ix_actividades_diagnostico_usuario_id'), 'actividades_diagnostico', ['usuario_id'], unique=False)

def downgrade() -> None:
    """Revierte los cambios del esquema."""
    # Gestiona downgrade.
    op.drop_index(op.f('ix_actividades_diagnostico_usuario_id'), table_name='actividades_diagnostico')
    op.drop_index('ix_actividades_diagnostico_usuario_creada', table_name='actividades_diagnostico')
    op.drop_index(op.f('ix_actividades_diagnostico_creada_en'), table_name='actividades_diagnostico')
    op.drop_index(op.f('ix_actividades_diagnostico_actividad_local_id'), table_name='actividades_diagnostico')
    op.drop_index(op.f('ix_actividades_diagnostico_actividad_id'), table_name='actividades_diagnostico')
    op.drop_table('actividades_diagnostico')
    op.drop_index(op.f('ix_usuarios_auth_social_usuario_id'), table_name='usuarios_auth_social')
    op.drop_table('usuarios_auth_social')
    op.drop_index(op.f('ix_sesiones_refresh_usuario_id'), table_name='sesiones_refresh')
    op.drop_index(op.f('ix_sesiones_refresh_revocada_en'), table_name='sesiones_refresh')
    op.drop_index(op.f('ix_sesiones_refresh_jti'), table_name='sesiones_refresh')
    op.drop_index(op.f('ix_sesiones_refresh_familia_id'), table_name='sesiones_refresh')
    op.drop_index(op.f('ix_sesiones_refresh_expira_en'), table_name='sesiones_refresh')
    op.drop_table('sesiones_refresh')
    op.drop_index(op.f('ix_actividades_usuario_id'), table_name='actividades')
    op.drop_index('ix_actividades_usuario_fecha', table_name='actividades')
    op.drop_index(op.f('ix_actividades_fecha_ruta'), table_name='actividades')
    op.drop_table('actividades')
    op.drop_index('uq_usuarios_nombre_usuario_lower', table_name='usuarios')
    op.drop_index('uq_usuarios_email_lower', table_name='usuarios')
    op.drop_index(op.f('ix_usuarios_total_metros'), table_name='usuarios')
    op.drop_table('usuarios')
