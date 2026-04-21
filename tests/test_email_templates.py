# tests/test_email_templates.py

"""Contiene pruebas automatizadas de este módulo."""

# Pruebas para services/email_templates.py.
# Verifica que la plantilla HTML contiene los datos dinámicos correctos.

from services.email_templates import recuperacion_password_template


class TestRecuperacionPasswordTemplate:
    """Agrupa pruebas relacionadas con recuperacion password template."""

    def test_contiene_codigo(self):
        """Verifica que contiene codigo."""
        html = recuperacion_password_template("123456", 15)
        assert "123456" in html

    def test_contiene_minutos(self):
        """Verifica que contiene minutos."""
        html = recuperacion_password_template("999999", 10)
        assert "10" in html

    def test_es_html_valido_basico(self):
        """Verifica que es html valido basico."""
        html = recuperacion_password_template("000000", 5)
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html

    def test_contiene_titulo_olvidaste_password(self):
        """Verifica que contiene titulo olvidaste password."""
        html = recuperacion_password_template("123456", 15)
        assert "Olvidaste tu contraseña" in html or "olvidaste" in html.lower()

    def test_contiene_referencia_logo_cid(self):
        """La plantilla referencia el logo embebido por CID."""
        html = recuperacion_password_template("123456", 15)
        assert "cid:moveon_logo" in html

    def test_contiene_copyright_moveon(self):
        """Verifica que contiene copyright moveon."""
        html = recuperacion_password_template("123456", 15)
        assert "MoveOn" in html

    def test_pluralizacion_1_minuto(self):
        """Con 1 minuto no debe decir 'minutos' (singular)."""
        html = recuperacion_password_template("123456", 1)
        # La plantilla usa: "minuto" + ("s" if minutos != 1 else "")
        assert "1 minuto<" in html or "1 minuto " in html

    def test_pluralizacion_varios_minutos(self):
        """Con >1 minutos debe usar plural."""
        html = recuperacion_password_template("123456", 15)
        assert "15 minutos" in html

    def test_codigo_diferente_se_refleja(self):
        """Dos códigos distintos generan HTML distinto en la parte del código."""
        html_a = recuperacion_password_template("111111", 15)
        html_b = recuperacion_password_template("222222", 15)
        assert "111111" in html_a
        assert "222222" in html_b
        assert "222222" not in html_a
