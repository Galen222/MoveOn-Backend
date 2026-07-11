# schemas.py

"""
Esquemas de Validación de Datos (Pydantic V2).

Define la estructura de los datos que entran y salen de la API,
asegurando que cumplan con las reglas de negocio antes de tocar la DB.
"""
from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    field_validator,
    model_validator,
    StrictInt,
    ConfigDict,
    AnyHttpUrl,
)
from datetime import date, datetime
from enum import Enum
from typing import Optional, Any, List
import re
from utils import validators
from exceptions import AppValidationError
from domain.enums import ProvinciaEspaña, GeneroUsuario, TipoActividad


class RespuestaHandshake(BaseModel):
    """Esquema para la respuesta del handshake inicial."""

    app_session_token: str


class Registro(BaseModel):
    """
    Esquema para validar los campos en el registro de un nuevo usuario.
    """

    nombre_usuario: str = Field(..., min_length=5, max_length=50)
    email: EmailStr
    password: str = Field(...)
    nombre_real: Optional[str] = None
    fecha_nacimiento: date
    genero: Optional[GeneroUsuario] = None
    altura: Optional[int] = None
    peso: Optional[float] = None
    provincia: Optional[ProvinciaEspaña] = None
    perfil_visible: bool = Field(default=True)
    acepta_terminos: bool = Field(...)
    fecha_aceptacion_terminos: datetime = Field(...)
    version_terminos: str = Field(..., max_length=10)

    @model_validator(mode="before")
    @classmethod
    def validar_campos_requeridos_registro(cls, values: Any) -> Any:
        """Comprueba presencia explícita de los campos obligatorios del registro.

        Se ejecuta en ``mode='before'`` porque el mensaje por defecto de
        Pydantic (``field required``) no tiene ``error_code`` y queremos que
        cada campo que falta devuelva un código distinto (``USERNAME_REQUIRED``,
        ``EMAIL_REQUIRED``, etc.) para que el cliente Android pueda resaltar
        exactamente el campo en rojo.

        Args:
            values: diccionario crudo de entrada tal como lo recibió Pydantic.

        Returns:
            El mismo ``values`` si todos los obligatorios están presentes.

        Raises:
            AppValidationError: con código específico por campo ausente (``USERNAME_REQUIRED``, ``EMAIL_REQUIRED``, ``PASSWORD_REQUIRED``, ``BIRTH_DATE_REQUIRED``).
        """
        # Valida campos requeridos registro.
        if isinstance(values, dict):
            if "nombre_usuario" not in values or not values["nombre_usuario"]:
                raise AppValidationError(
                    "Error: El nombre de usuario es obligatorio", "USERNAME_REQUIRED"
                )
            if "email" not in values or not values["email"]:
                raise AppValidationError(
                    "Error: El email es obligatorio", "EMAIL_REQUIRED"
                )
            if "password" not in values or not values["password"]:
                raise AppValidationError(
                    "Error: La contraseña es obligatoria", "PASSWORD_REQUIRED"
                )
            if "fecha_nacimiento" not in values:
                raise AppValidationError(
                    "Error: La fecha de nacimiento es obligatoria",
                    "BIRTH_DATE_REQUIRED",
                )
        return values

    @field_validator("nombre_usuario")
    @classmethod
    def validar_nombre_usuario(cls, valor: str) -> str:
        # Quitar espacios.
        """Valida el nombre de usuario: longitud y alfanumérico estricto.

        Recorta espacios, exige longitud entre 5 y 50 y restringe a
        ``[A-Za-z0-9]``. Sin espacios ni símbolos: el nombre se usa en URLs
        públicas (``/perfil/informacion/<nombre>``), menciones y búsqueda
        case-insensitive, por lo que limitar a alfanumérico simplifica
        encoding y evita colisiones con caracteres raros.

        Args:
            valor: nombre de usuario propuesto.

        Returns:
            El nombre ya recortado si pasa todas las comprobaciones.

        Raises:
            AppValidationError: ``USERNAME_TOO_SHORT`` si tiene menos de 5 caracteres.
            AppValidationError: ``USERNAME_TOO_LONG`` si supera los 50.
            AppValidationError: ``USERNAME_INVALID_FORMAT`` si contiene algo que no sea alfanumérico.
        """
        valor = valor.strip()
        # Validación de longitud mínima.
        if len(valor) < 5:
            raise AppValidationError(
                "Error: El nombre de usuario debe tener al menos 5 caracteres",
                "USERNAME_TOO_SHORT",
            )

        if len(valor) > 50:  # ✅ añadido
            raise AppValidationError(
                "Error: El nombre de usuario no puede superar los 50 caracteres",
                "USERNAME_TOO_LONG",
            )
        # Validación formato alfanumérico sin espacios.
        if not re.match("^[a-zA-Z0-9]*$", valor):
            raise AppValidationError(
                "Error: El nombre de usuario solo puede contener letras y números",
                "USERNAME_INVALID_FORMAT",
            )
        return valor

    @field_validator("nombre_real")
    @classmethod
    def validar_nombre_real_registro(cls, v):
        """Valida el nombre real opcional delegando en la lógica compartida.

        Admite ``None`` porque el campo no es obligatorio en el registro.
        Si hay valor, lo recorta y delega en ``validators.validar_nombre_real_logica``,
        que impone longitud, caracteres latinos permitidos, espacios,
        apóstrofes y guiones (ver ``utils/validators.py``).

        Args:
            v: nombre real o ``None``.

        Returns:
            Nombre real recortado, o ``None`` si no se proporcionó.

        Raises:
            AppValidationError: las que levante ``validar_nombre_real_logica``.
        """
        if v is None:
            return v
        v = v.strip()
        return validators.validar_nombre_real_logica(v)

    @field_validator("email", mode="before")
    @classmethod
    def validar_email_registro(cls, valor: Any) -> Any:
        """Normaliza el email a minúsculas y recorta espacios antes de parsear.

        Se ejecuta en ``mode='before'`` para que la validación posterior de
        ``EmailStr`` vea siempre la forma canónica. Trabajar en minúsculas
        simplifica comparaciones y elimina duplicados espurios
        (``John@X.com`` vs ``john@x.com``).

        Args:
            valor: valor crudo del campo ``email``.

        Returns:
            Cadena en minúsculas recortada, o el valor tal cual si no es cadena.
        """
        if isinstance(valor, str):
            return valor.lower().strip()
        return valor

    @field_validator("email", mode="wrap")
    @classmethod
    def validar_email_registro_custom(cls, v, handler):
        """Sustituye el error de ``EmailStr`` por un ``AppValidationError`` con código.

        ``EmailStr`` de Pydantic devuelve un mensaje genérico sin código.
        Esta envoltura (``mode='wrap'``) captura cualquier error del handler
        original y lo re-lanza como ``EMAIL_FORMAT_INVALID`` para que el
        cliente Android detecte el campo problemático programáticamente.

        Args:
            v: valor a validar.
            handler: validador original de ``EmailStr`` encadenado por Pydantic.

        Returns:
            Email ya validado por ``EmailStr`` si la validación pasa.

        Raises:
            AppValidationError: ``EMAIL_FORMAT_INVALID`` si el formato no es un email válido.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "EMAIL_FORMAT_INVALID",
            "Error: El formato del correo electrónico no es válido",
        )

    @field_validator("password")
    @classmethod
    def validar_password_registro(cls, v):
        """Aplica la política de contraseñas al campo ``password`` del registro.

        Delega en ``validators.validar_password_logica``, que exige longitud
        mínima de 8, máximo de 72 bytes UTF-8 (límite de bcrypt), al menos
        una mayúscula y al menos un dígito.

        Args:
            v: contraseña en claro tal como la introdujo el usuario.

        Returns:
            La misma contraseña si pasa todas las comprobaciones.

        Raises:
            AppValidationError: códigos ``PASSWORD_TOO_SHORT``, ``PASSWORD_TOO_LONG_BYTES``, ``PASSWORD_MISSING_UPPERCASE`` o ``PASSWORD_MISSING_NUMBER``.
        """
        return validators.validar_password_logica(v)

    @field_validator("fecha_nacimiento", mode="wrap")
    @classmethod
    def validar_fecha_nacimiento_registro_custom(cls, v, handler):
        """Intercepta el error de parseo de fecha para unificar el mensaje.

        Pydantic acepta varios formatos de fecha pero su error por defecto
        no trae ``error_code``. Este wrapper fuerza ``VALIDATION_ERROR`` y
        un mensaje en español que dice explícitamente el formato esperado
        (``AAAA-MM-DD``).

        Args:
            v: valor crudo del campo ``fecha_nacimiento``.
            handler: validador original encadenado por Pydantic.

        Returns:
            Fecha ya parseada si el handler acepta el formato.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si el valor no es una fecha válida.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La fecha debe tener formato AAAA-MM-DD",
        )

    @field_validator("fecha_nacimiento")
    @classmethod
    def validar_fecha_nacimiento_registro(cls, v):
        """Aplica la regla de edad mínima (18 años) a la fecha de nacimiento.

        Delega en ``validators.validar_fecha_nacimiento_logica``, que además
        rechaza fechas futuras y calcula la edad por comparación de
        ``(mes, día)`` para no tener errores de un día alrededor del cumpleaños.

        Args:
            v: fecha de nacimiento ya parseada.

        Returns:
            La misma fecha si pasa la regla.

        Raises:
            AppValidationError: ``BIRTH_DATE_IN_FUTURE`` o ``AGE_RESTRICTION_NOT_MET``.
        """
        return validators.validar_fecha_nacimiento_logica(v)

    @field_validator("genero", mode="wrap")
    @classmethod
    def validar_genero_registro_custom(cls, v, handler):
        """Intercepta errores de parseo del enum ``GeneroUsuario``.

        Pydantic devolvería "value is not a valid enumeration member", que
        no es muy útil en una UI. Este wrapper responde con
        ``VALIDATION_ERROR`` y un texto adaptado.

        Args:
            v: valor crudo del campo ``genero``.
            handler: validador original del enum.

        Returns:
            Valor ya validado por el enum si pasa.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si el valor no pertenece al enum.
        """
        return validators.interceptar_error_pydantic(
            v, handler, "VALIDATION_ERROR", "Error: El género seleccionado no es válido"
        )

    @field_validator("altura", mode="wrap")
    @classmethod
    def validar_altura_registro_custom(cls, v, handler):
        """Intercepta errores de tipo al parsear ``altura`` como entero.

        Si el cliente envía una cadena no numérica o un float, Pydantic
        falla con un mensaje técnico. Aquí se traduce a un mensaje humano
        con ``VALIDATION_ERROR``.

        Args:
            v: valor crudo del campo ``altura``.
            handler: validador original de enteros.

        Returns:
            Entero ya validado si pasa.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si el valor no se puede interpretar como entero.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La altura debe ser un número entero en centimetros",
        )

    @field_validator("altura")
    @classmethod
    def validar_altura_registro(cls, v):
        """Aplica el rango humano razonable a la altura (50–300 cm).

        Delega en ``validators.validar_altura_logica``. ``None`` se acepta
        para permitir no rellenar el campo.

        Args:
            v: altura en centímetros, o ``None``.

        Returns:
            El mismo valor si pasa el rango.

        Raises:
            AppValidationError: ``HEIGHT_OUT_OF_RANGE`` si no está en [50, 300].
        """
        return validators.validar_altura_logica(v)

    @field_validator("peso", mode="wrap")
    @classmethod
    def validar_peso_registro_custom(cls, v, handler):
        """Intercepta errores de tipo al parsear ``peso`` como número.

        Usa el código específico ``WEIGHT_MUST_BE_KILOGRAM_NUMBER`` (no el
        genérico ``VALIDATION_ERROR``) para que la UI pueda mostrar un
        texto específico del campo.

        Args:
            v: valor crudo del campo ``peso``.
            handler: validador original.

        Returns:
            Número ya validado si pasa.

        Raises:
            AppValidationError: ``WEIGHT_MUST_BE_KILOGRAM_NUMBER`` si no es numérico.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "WEIGHT_MUST_BE_KILOGRAM_NUMBER",
            "Error: El peso debe ser un número en kilos",
        )

    @field_validator("peso")
    @classmethod
    def validar_peso_registro(cls, v):
        """Aplica el rango humano razonable al peso (20–300 kg).

        Delega en ``validators.validar_peso_logica``. ``None`` se acepta
        para permitir no rellenar el campo.

        Args:
            v: peso en kilogramos, o ``None``.

        Returns:
            El mismo valor si pasa el rango.

        Raises:
            AppValidationError: ``WEIGHT_OUT_OF_RANGE`` si no está en [20, 300].
        """
        return validators.validar_peso_logica(v)

    @field_validator("provincia", mode="wrap")
    @classmethod
    def validar_provincia_registro_custom(cls, v, handler):
        """Intercepta errores de parseo del enum ``ProvinciaEspaña``.

        La lista de provincias es cerrada; si el cliente envía algo fuera
        de ella, este wrapper responde con ``VALIDATION_ERROR`` y un mensaje
        genérico de "ubicación no válida" en vez del error técnico de enum.

        Args:
            v: valor crudo del campo ``provincia``.
            handler: validador original del enum.

        Returns:
            Valor ya validado por el enum si pasa.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si no pertenece al enum.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La ubicación seleccionada no es válida",
        )

    @field_validator("perfil_visible", mode="wrap")
    @classmethod
    def validar_perfil_visible_registro_custom(cls, v, handler):
        """Intercepta errores de parseo del booleano ``perfil_visible``.

        Pydantic acepta varios valores como booleanos (``"true"``, ``1``);
        si llega algo fuera de esa lista, se traduce el error a
        ``VALIDATION_ERROR`` con mensaje en español.

        Args:
            v: valor crudo.
            handler: validador original.

        Returns:
            Booleano ya validado si pasa.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si no se puede interpretar como booleano.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: El formato de perfil visible no es válido",
        )

    @field_validator("acepta_terminos")
    @classmethod
    def validar_acepta_terminos(cls, v: bool) -> bool:
        """Exige aceptación explícita de términos y política de privacidad.

        No basta con que el campo esté presente: tiene que ser ``True``.
        Es el consentimiento que soporta legalmente el registro; si llega
        ``False`` (o el cliente manda el campo pero lo desmarcó), se aborta
        el alta con un código específico para que el cliente muestre el
        diálogo legal.

        Args:
            v: valor del checkbox de aceptación.

        Returns:
            ``True`` si la aceptación es válida.

        Raises:
            AppValidationError: ``REGISTRATION_CONSENTS_REQUIRED`` si no se aceptan los términos.
        """
        if not v:
            raise AppValidationError(
                "Error: Debes aceptar los Términos y la Política de Privacidad para registrarte",
                "REGISTRATION_CONSENTS_REQUIRED",
            )
        return v

    @field_validator("fecha_aceptacion_terminos", mode="wrap")
    @classmethod
    def validar_fecha_aceptacion_terminos_custom(cls, v, handler):
        """Intercepta errores de parseo ISO-8601 del timestamp de aceptación.

        Pydantic acepta varios formatos de datetime pero queremos un mensaje
        consistente con el resto de fechas del API (``VALIDATION_ERROR`` y
        texto claro en español).

        Args:
            v: valor crudo.
            handler: validador original.

        Returns:
            ``datetime`` ya parseado si el formato es válido.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si el formato no es ISO-8601.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La fecha de aceptación debe tener formato ISO-8601",
        )

    @field_validator("fecha_aceptacion_terminos")
    @classmethod
    def validar_fecha_aceptacion_terminos(cls, v: datetime) -> datetime:
        """Normaliza a UTC la fecha de aceptación y rechaza valores futuros.

        Si el ``datetime`` llega naive, se asume UTC (es lo que envía la
        app Android). Se admite hasta 5 minutos de margen futuro para
        absorber pequeños desajustes de reloj entre el dispositivo y el
        servidor; a partir de ahí se considera sospechoso y se rechaza.

        Args:
            v: ``datetime`` ya parseado.

        Returns:
            El mismo ``datetime`` normalizado a UTC.

        Raises:
            AppValidationError: ``TERMS_ACCEPTED_AT_IN_FUTURE`` si el instante supera (``ahora + 5 minutos``).
        """
        from datetime import timedelta, timezone

        ahora = datetime.now(timezone.utc)
        v_utc = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if v_utc > ahora + timedelta(minutes=5):
            raise AppValidationError(
                "Error: La fecha de aceptación no puede ser futura",
                "TERMS_ACCEPTED_AT_IN_FUTURE",
            )
        return v_utc

    @field_validator("version_terminos")
    @classmethod
    def validar_version_terminos(cls, v: str) -> str:
        """Valida que la versión de términos no llegue vacía tras recortar.

        La app Android envía la versión real del documento legal que se
        mostró al usuario (p. ej. ``"1.2"``). Aquí solo se normaliza y se
        exige no vacío; la comprobación de que la versión sea *la esperada*
        queda en manos de otra capa (para no invalidar registros si se
        cambia la versión en medio del flujo).

        Args:
            v: cadena con la versión declarada por el cliente.

        Returns:
            Versión recortada de espacios.

        Raises:
            AppValidationError: ``TERMS_VERSION_REQUIRED`` si queda vacía tras recortar.
        """
        v = v.strip()
        if not v:
            raise AppValidationError(
                "Error: La versión de los términos es obligatoria",
                "TERMS_VERSION_REQUIRED",
            )
        return v


class RespuestaRegistro(BaseModel):
    """Representa respuesta registro."""

    estatus: str
    mensaje: str
    nombre_usuario: str


class ProveedorAuthSocial(str, Enum):
    """Representa proveedor autenticación social."""

    GOOGLE = "google"


class LoginSocial(BaseModel):
    """Representa login social."""

    provider: ProveedorAuthSocial
    token: str

    @model_validator(mode="before")
    @classmethod
    def validar_campos_requeridos_login_social(cls, values: Any) -> Any:
        """Comprueba presencia explícita de ``provider`` y ``token``.

        Aunque los campos son obligatorios en la definición, el mensaje por
        defecto de Pydantic no lleva ``error_code``. Este pre-validador
        asegura códigos específicos (``SOCIAL_PROVIDER_REQUIRED``,
        ``SOCIAL_TOKEN_REQUIRED``) para que el cliente sepa qué campo falta.

        Args:
            values: diccionario crudo de entrada.

        Returns:
            El mismo ``values`` si todos los obligatorios están presentes.

        Raises:
            AppValidationError: ``SOCIAL_PROVIDER_REQUIRED`` si falta el proveedor.
            AppValidationError: ``SOCIAL_TOKEN_REQUIRED`` si falta el token.
        """
        if isinstance(values, dict):
            if "provider" not in values or not values["provider"]:
                raise AppValidationError(
                    "Error: El proveedor social es obligatorio",
                    "SOCIAL_PROVIDER_REQUIRED",
                )
            if "token" not in values or not values["token"]:
                raise AppValidationError(
                    "Error: El token social es obligatorio",
                    "SOCIAL_TOKEN_REQUIRED",
                )
        return values

    @field_validator("token", mode="before")
    @classmethod
    def limpiar_token_social(cls, valor: Any) -> Any:
        """Recorta el token social y rechaza cadenas vacías tras el recorte.

        El cliente puede enviar el token con espacios accidentales al
        copiar/pegar en builds de desarrollo. Recortar aquí evita que una
        cadena solo de espacios llegue al verificador de Google como token
        válido y desperdicie una llamada a JWKS.

        Args:
            valor: token tal como llega del cliente.

        Returns:
            Token recortado si es cadena; el valor crudo si no lo es.

        Raises:
            AppValidationError: ``SOCIAL_TOKEN_EMPTY`` si tras recortar queda vacío.
        """
        if isinstance(valor, str):
            valor_limpio = valor.strip()
            if not valor_limpio:
                raise AppValidationError(
                    "Error: El token social no puede estar vacío",
                    "SOCIAL_TOKEN_EMPTY",
                )
            return valor_limpio
        return valor


class RegistroSocial(BaseModel):
    """Representa registro social."""

    provider: ProveedorAuthSocial
    token: str
    nombre_usuario: str = Field(..., min_length=5, max_length=50)
    fecha_nacimiento: date
    perfil_visible: bool = Field(default=True)
    acepta_terminos: bool = Field(...)
    fecha_aceptacion_terminos: datetime = Field(...)
    version_terminos: str = Field(..., max_length=10)

    @model_validator(mode="before")
    @classmethod
    def validar_campos_requeridos_registro_social(cls, values: Any) -> Any:
        """Comprueba presencia de los obligatorios del registro social.

        Mismo patrón que el registro clásico pero con el subconjunto de
        campos propios del flujo social: además de ``provider``/``token``
        exige ``nombre_usuario`` (lo elige el usuario, no viene del proveedor)
        y ``fecha_nacimiento`` (para comprobar la mayoría de edad).

        Args:
            values: diccionario crudo de entrada.

        Returns:
            El mismo ``values`` si todos los obligatorios están presentes.

        Raises:
            AppValidationError: con códigos ``SOCIAL_PROVIDER_REQUIRED``, ``SOCIAL_TOKEN_REQUIRED``, ``USERNAME_REQUIRED`` o ``BIRTH_DATE_REQUIRED`` según qué falte.
        """
        # Valida campos requeridos registro social.
        if isinstance(values, dict):
            if "provider" not in values or not values["provider"]:
                raise AppValidationError(
                    "Error: El proveedor social es obligatorio",
                    "SOCIAL_PROVIDER_REQUIRED",
                )
            if "token" not in values or not values["token"]:
                raise AppValidationError(
                    "Error: El token social es obligatorio",
                    "SOCIAL_TOKEN_REQUIRED",
                )
            if "nombre_usuario" not in values or not values["nombre_usuario"]:
                raise AppValidationError(
                    "Error: El nombre de usuario es obligatorio",
                    "USERNAME_REQUIRED",
                )
            if "fecha_nacimiento" not in values:
                raise AppValidationError(
                    "Error: La fecha de nacimiento es obligatoria",
                    "BIRTH_DATE_REQUIRED",
                )
        return values

    @field_validator("token", mode="before")
    @classmethod
    def limpiar_token_registro_social(cls, valor: Any) -> Any:
        """Recorta el token social del registro y rechaza cadenas vacías.

        Idéntica lógica a ``LoginSocial.limpiar_token_social`` pero
        duplicada aquí para no acoplar los dos esquemas; pueden evolucionar
        de forma independiente si en el futuro los formatos divergen.

        Args:
            valor: token tal como llega del cliente.

        Returns:
            Token recortado si es cadena; el valor crudo si no lo es.

        Raises:
            AppValidationError: ``SOCIAL_TOKEN_EMPTY`` si tras recortar queda vacío.
        """
        if isinstance(valor, str):
            valor_limpio = valor.strip()
            if not valor_limpio:
                raise AppValidationError(
                    "Error: El token social no puede estar vacío",
                    "SOCIAL_TOKEN_EMPTY",
                )
            return valor_limpio
        return valor

    @field_validator("nombre_usuario")
    @classmethod
    def validar_nombre_usuario_social(cls, valor: str) -> str:
        """Valida el nombre de usuario elegido en el registro social.

        Replica las reglas de ``Registro.validar_nombre_usuario`` (longitud
        5–50 y alfanumérico estricto). Se duplica la lógica en vez de
        extraerla a una función compartida para que cada esquema pueda
        evolucionar por separado (p. ej. suavizar reglas solo en social).

        Args:
            valor: nombre de usuario propuesto.

        Returns:
            Nombre ya recortado si pasa todas las comprobaciones.

        Raises:
            AppValidationError: ``USERNAME_TOO_SHORT``, ``USERNAME_TOO_LONG`` o ``USERNAME_INVALID_FORMAT`` según el fallo.
        """
        # Valida nombre usuario social.
        valor = valor.strip()
        if len(valor) < 5:
            raise AppValidationError(
                "Error: El nombre de usuario debe tener al menos 5 caracteres",
                "USERNAME_TOO_SHORT",
            )
        if len(valor) > 50:
            raise AppValidationError(
                "Error: El nombre de usuario no puede superar los 50 caracteres",
                "USERNAME_TOO_LONG",
            )
        if not re.match("^[a-zA-Z0-9]*$", valor):
            raise AppValidationError(
                "Error: El nombre de usuario solo puede contener letras y números",
                "USERNAME_INVALID_FORMAT",
            )
        return valor

    @field_validator("fecha_nacimiento", mode="wrap")
    @classmethod
    def validar_fecha_nacimiento_social_custom(cls, v, handler):
        """Intercepta el error de parseo de fecha en registro social.

        Mismo comportamiento que el equivalente de ``Registro`` pero
        duplicado aquí para no acoplar ambos esquemas en un único validador
        compartido.

        Args:
            v: valor crudo del campo ``fecha_nacimiento``.
            handler: validador original encadenado por Pydantic.

        Returns:
            Fecha ya parseada si el handler acepta el formato.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si el valor no es una fecha válida.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La fecha debe tener formato AAAA-MM-DD",
        )

    @field_validator("fecha_nacimiento")
    @classmethod
    def validar_fecha_nacimiento_social(cls, v):
        """Aplica la regla de edad mínima (18 años) a la fecha de nacimiento social.

        Delega en ``validators.validar_fecha_nacimiento_logica``, igual que el
        registro clásico.

        Args:
            v: fecha de nacimiento ya parseada.

        Returns:
            La misma fecha si pasa la regla.

        Raises:
            AppValidationError: ``BIRTH_DATE_IN_FUTURE`` o ``AGE_RESTRICTION_NOT_MET``.
        """
        return validators.validar_fecha_nacimiento_logica(v)

    @field_validator("perfil_visible", mode="wrap")
    @classmethod
    def validar_perfil_visible_social_custom(cls, v, handler):
        """Intercepta errores de parseo del booleano ``perfil_visible``.

        Equivalente a la versión de ``Registro``; ver ``validar_perfil_visible_registro_custom``
        para el razonamiento sobre por qué se duplica la lógica.

        Args:
            v: valor crudo.
            handler: validador original.

        Returns:
            Booleano ya validado si pasa.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si no se puede interpretar como booleano.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: El formato de perfil visible no es válido",
        )

    @field_validator("acepta_terminos")
    @classmethod
    def validar_acepta_terminos_social(cls, v: bool) -> bool:
        """Exige aceptación explícita de términos también en el registro social.

        Aunque el usuario se autentique con Google, el alta en MoveOn
        requiere aceptar los términos propios del servicio: se valida aquí
        con el mismo código ``REGISTRATION_CONSENTS_REQUIRED`` para que la
        UI pueda reutilizar el mismo diálogo legal.

        Args:
            v: valor del checkbox de aceptación.

        Returns:
            ``True`` si la aceptación es válida.

        Raises:
            AppValidationError: ``REGISTRATION_CONSENTS_REQUIRED`` si el usuario no aceptó.
        """
        if not v:
            raise AppValidationError(
                "Error: Debes aceptar los Términos y la Política de Privacidad para registrarte",
                "REGISTRATION_CONSENTS_REQUIRED",
            )
        return v

    @field_validator("fecha_aceptacion_terminos", mode="wrap")
    @classmethod
    def validar_fecha_aceptacion_terminos_social_custom(cls, v, handler):
        """Intercepta errores de parseo ISO-8601 del timestamp social.

        Equivalente a la versión de ``Registro``; ver
        ``validar_fecha_aceptacion_terminos_custom`` para los motivos del
        reemplazo de mensaje.

        Args:
            v: valor crudo.
            handler: validador original.

        Returns:
            ``datetime`` ya parseado si el formato es válido.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si el formato no es ISO-8601.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La fecha de aceptación debe tener formato ISO-8601",
        )

    @field_validator("fecha_aceptacion_terminos")
    @classmethod
    def validar_fecha_aceptacion_terminos_social(cls, v: datetime) -> datetime:
        """Normaliza a UTC y rechaza timestamps futuros en registro social.

        Mismo margen de 5 minutos de tolerancia futura que el registro
        clásico, para absorber desajustes de reloj.

        Args:
            v: ``datetime`` ya parseado.

        Returns:
            El mismo ``datetime`` normalizado a UTC.

        Raises:
            AppValidationError: ``TERMS_ACCEPTED_AT_IN_FUTURE`` si supera (``ahora + 5 minutos``).
        """
        from datetime import timedelta, timezone

        ahora = datetime.now(timezone.utc)
        v_utc = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if v_utc > ahora + timedelta(minutes=5):
            raise AppValidationError(
                "Error: La fecha de aceptación no puede ser futura",
                "TERMS_ACCEPTED_AT_IN_FUTURE",
            )
        return v_utc

    @field_validator("version_terminos")
    @classmethod
    def validar_version_terminos_social(cls, v: str) -> str:
        """Recorta y valida no-vacío la versión de términos en registro social.

        Mismo contrato que en ``Registro.validar_version_terminos``: solo
        recorta y exige no vacío, sin comprobar que la versión sea *la
        esperada*.

        Args:
            v: cadena con la versión.

        Returns:
            Versión recortada de espacios.

        Raises:
            AppValidationError: ``TERMS_VERSION_REQUIRED`` si queda vacía tras recortar.
        """
        v = v.strip()
        if not v:
            raise AppValidationError(
                "Error: La versión de los términos es obligatoria",
                "TERMS_VERSION_REQUIRED",
            )
        return v


class Login(BaseModel):
    """Esquema para validar las credenciales en el inicio de sesión."""

    identificador: str
    password: str

    @model_validator(mode="before")
    @classmethod
    def validar_campos_requeridos_login(cls, values: Any) -> Any:
        """Comprueba presencia explícita de ``identificador`` y ``password``.

        Igual que el resto de pre-validadores, intercepta los obligatorios
        antes de Pydantic para que cada ausencia tenga su propio código
        (``IDENTIFIER_REQUIRED``, ``PASSWORD_REQUIRED``).

        Args:
            values: diccionario crudo de entrada.

        Returns:
            El mismo ``values`` si todos los obligatorios están presentes.

        Raises:
            AppValidationError: ``IDENTIFIER_REQUIRED`` o ``PASSWORD_REQUIRED`` según qué falte.
        """
        if isinstance(values, dict):
            if "identificador" not in values or not values["identificador"]:
                raise AppValidationError(
                    "Error: El identificador es obligatorio", "IDENTIFIER_REQUIRED"
                )
            if "password" not in values or not values["password"]:
                raise AppValidationError(
                    "Error: La contraseña es obligatoria", "PASSWORD_REQUIRED"
                )
        return values

    @field_validator("identificador", mode="before")
    @classmethod
    def limpiar_identificador(cls, valor: Any) -> Any:
        """Recorta espacios del identificador (email o nombre de usuario).

        No normaliza a minúsculas aquí porque el servicio
        (``access_service.buscar_por_identificador``) ya hace la comparación
        case-insensitive con ``LOWER(columna)``; bajar aquí a minúsculas
        escondería inputs que en realidad son errores del cliente.

        Args:
            valor: identificador crudo.

        Returns:
            Identificador recortado si es cadena; el valor crudo si no lo es.

        Raises:
            AppValidationError: ``IDENTIFIER_EMPTY`` si tras recortar queda vacío.
        """
        if isinstance(valor, str):
            # Quitar espacios.
            valor_limpio = valor.strip()
            if not valor_limpio:
                raise AppValidationError(
                    "Error: El identificador no puede estar vacío", "IDENTIFIER_EMPTY"
                )
            return valor_limpio
        return valor


class RespuestaLogin(BaseModel):
    """Representa respuesta login."""

    estatus: str
    nombre_usuario: str
    token_acceso: str
    refresh_token: str


class SolicitudRefreshToken(BaseModel):
    """Representa solicitud refresco token."""

    refresh_token: str = Field(...)

    @model_validator(mode="before")
    @classmethod
    def validar_campos_requeridos_refresh(cls, values: Any) -> Any:
        """Comprueba presencia explícita de ``refresh_token``.

        Mismo patrón que el resto de pre-validadores: intercepta antes de
        que Pydantic devuelva el error genérico, para asignar el código
        ``REFRESH_TOKEN_REQUIRED``.

        Args:
            values: diccionario crudo de entrada.

        Returns:
            El mismo ``values`` si el campo está presente.

        Raises:
            AppValidationError: ``REFRESH_TOKEN_REQUIRED`` si el campo falta o está vacío.
        """
        if isinstance(values, dict):
            if "refresh_token" not in values or not values["refresh_token"]:
                raise AppValidationError(
                    "Error: El refresh token es obligatorio", "REFRESH_TOKEN_REQUIRED"
                )
        return values

    @field_validator("refresh_token", mode="before")
    @classmethod
    def limpiar_refresh_token(cls, valor: Any) -> Any:
        """Recorta el refresh token y rechaza cadenas vacías tras el recorte.

        El token es una cadena JWT; un espacio al principio o al final
        rompería el parseo posterior. Recortar aquí libera a los
        verificadores JWT aguas abajo de esa preocupación.

        Args:
            valor: refresh token tal como llega del cliente.

        Returns:
            Token recortado si es cadena; el valor crudo si no lo es.

        Raises:
            AppValidationError: ``REFRESH_TOKEN_EMPTY`` si tras recortar queda vacío.
        """
        if isinstance(valor, str):
            valor_limpio = valor.strip()
            if not valor_limpio:
                raise AppValidationError(
                    "Error: El refresh token no puede estar vacío",
                    "REFRESH_TOKEN_EMPTY",
                )
            return valor_limpio
        return valor


class RespuestaRefreshToken(BaseModel):
    """Representa respuesta refresco token."""

    estatus: str
    nombre_usuario: str
    token_acceso: str
    refresh_token: str


class SolicitudLogout(SolicitudRefreshToken):
    """Recibe el refresh token para revocar la sesión actual."""

    pass


class RespuestaInformacionPerfil(BaseModel):
    """Representa respuesta informacion perfil."""

    model_config = ConfigDict(from_attributes=True)

    nombre_usuario: str
    nombre_real: Optional[str] = None
    email: EmailStr
    fecha_nacimiento: date
    genero: Optional[str] = None
    altura: Optional[int] = None
    peso: Optional[float] = None
    provincia: Optional[str] = None
    foto_perfil: Optional[str] = None
    foto_version: int = 0
    perfil_visible: bool
    total_puntos: int
    total_calorias: int = 0
    total_calorias: int = 0
    total_duracion_segundos: int = 0
    total_actividades: int = 0
    objetivo_semanal_metros: int = 50000
    objetivo_semanal_metros: int = 50000
    objetivo_mensual_metros: int = 150000


class ActualizarPerfil(BaseModel):
    """Esquema para actualizaciones del perfil de usuario."""

    nombre_real: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    genero: Optional[GeneroUsuario] = None
    altura: Optional[int] = None
    peso: Optional[float] = None
    provincia: Optional[ProvinciaEspaña] = None
    perfil_visible: Optional[bool] = None
    objetivo_semanal_metros: Optional[int] = None
    objetivo_mensual_metros: Optional[int] = None

    @field_validator("nombre_real")
    @classmethod
    def validar_nombre_real_actualizacion(cls, v):
        """Valida el nombre real opcional en el flujo de actualización.

        ``None`` significa "no tocar este campo" (el PATCH es parcial) y se
        devuelve tal cual para que el servicio no lo escriba. Si hay valor,
        se recorta y se delega en la lógica compartida.

        Args:
            v: nombre real o ``None``.

        Returns:
            Nombre recortado, o ``None`` si no se proporcionó.

        Raises:
            AppValidationError: las que levante ``validators.validar_nombre_real_logica``.
        """
        if v is None:
            return v
        v = v.strip()
        return validators.validar_nombre_real_logica(v)

    @field_validator("email", mode="before")
    @classmethod
    def validar_email_actualizacion(cls, v):
        """Normaliza el email a minúsculas y recorta espacios antes de parsear.

        Respeta ``None`` (campo opcional en PATCH). Si hay valor se baja
        a minúsculas para mantener la forma canónica en la base de datos
        y simplificar la detección de duplicados.

        Args:
            v: valor crudo del campo ``email`` o ``None``.

        Returns:
            Cadena en minúsculas recortada, ``None`` si venía ``None``, o el valor tal cual si no era cadena.
        """
        if v is not None and isinstance(v, str):
            return v.lower().strip()
        return v

    @field_validator("email", mode="wrap")
    @classmethod
    def validar_email_actualizacion_custom(cls, v, handler):
        """Sustituye el error de ``EmailStr`` por un ``AppValidationError``.

        Mismo motivo que en ``Registro``: ``EmailStr`` no trae ``error_code``
        y la UI necesita distinguir este fallo concreto para marcar el campo
        en rojo.

        Args:
            v: valor a validar.
            handler: validador original de ``EmailStr``.

        Returns:
            Email ya validado si pasa.

        Raises:
            AppValidationError: ``EMAIL_FORMAT_INVALID`` si el formato no es válido.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "EMAIL_FORMAT_INVALID",
            "Error: El formato del correo electrónico no es válido",
        )

    @field_validator("password")
    @classmethod
    def validar_password_actualizacion(cls, v):
        """Aplica la política de contraseñas solo si se está cambiando.

        Como el PATCH es parcial, ``None`` significa "no cambiar la contraseña"
        y se devuelve tal cual. Cuando sí hay valor, se delega en
        ``validators.validar_password_logica``.

        Args:
            v: contraseña nueva o ``None``.

        Returns:
            La contraseña si pasa las comprobaciones; ``None`` si no se cambia.

        Raises:
            AppValidationError: ``PASSWORD_TOO_SHORT``, ``PASSWORD_TOO_LONG_BYTES``, ``PASSWORD_MISSING_UPPERCASE`` o ``PASSWORD_MISSING_NUMBER``.
        """
        return validators.validar_password_logica(v) if v is not None else v

    @field_validator("fecha_nacimiento", mode="wrap")
    @classmethod
    def validar_fecha_nacimiento_actualizacion_custom(cls, v, handler):
        """Intercepta errores de parseo de fecha en el PATCH del perfil.

        Replica el comportamiento de ``Registro.validar_fecha_nacimiento_registro_custom``.

        Args:
            v: valor crudo.
            handler: validador original encadenado por Pydantic.

        Returns:
            Fecha ya parseada si el handler acepta el formato.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si el valor no es una fecha válida.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La fecha debe tener formato AAAA-MM-DD",
        )

    @field_validator("fecha_nacimiento")
    @classmethod
    def validar_fecha_nacimiento_actualizacion(cls, v):
        """Aplica la regla de edad mínima (18 años) si se intenta cambiar la fecha.

        Respeta ``None`` (no cambiar). Si hay valor, delega en
        ``validators.validar_fecha_nacimiento_logica``.

        Args:
            v: fecha de nacimiento ya parseada, o ``None``.

        Returns:
            La misma fecha si pasa; ``None`` si no se cambia.

        Raises:
            AppValidationError: ``BIRTH_DATE_IN_FUTURE`` o ``AGE_RESTRICTION_NOT_MET``.
        """
        return validators.validar_fecha_nacimiento_logica(v) if v is not None else v

    @field_validator("genero", mode="wrap")
    @classmethod
    def validar_genero_actualizacion_custom(cls, v, handler):
        """Intercepta errores de parseo del enum ``GeneroUsuario`` en el PATCH.

        Equivalente al del registro; mantiene consistencia en los mensajes
        entre alta y actualización.

        Args:
            v: valor crudo.
            handler: validador original del enum.

        Returns:
            Valor ya validado por el enum si pasa.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si no pertenece al enum.
        """
        return validators.interceptar_error_pydantic(
            v, handler, "VALIDATION_ERROR", "Error: El género seleccionado no es válido"
        )

    @field_validator("altura", mode="wrap")
    @classmethod
    def validar_altura_actualizacion_custom(cls, v, handler):
        """Intercepta errores de tipo al parsear ``altura`` como entero en PATCH.

        Mismo comportamiento que en el registro.

        Args:
            v: valor crudo.
            handler: validador original de enteros.

        Returns:
            Entero ya validado si pasa.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si el valor no es interpretable como entero.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La altura debe ser un número entero en cm",
        )

    @field_validator("altura")
    @classmethod
    def validar_altura_actualizacion(cls, v):
        """Aplica el rango humano razonable a la altura en el PATCH.

        Delega en ``validators.validar_altura_logica`` (admite ``None``).

        Args:
            v: altura en centímetros, o ``None``.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``HEIGHT_OUT_OF_RANGE`` si no está en [50, 300].
        """
        return validators.validar_altura_logica(v)

    @field_validator("peso", mode="wrap")
    @classmethod
    def validar_peso_actualizacion_custom(cls, v, handler):
        """Intercepta errores de tipo al parsear ``peso`` como número en PATCH.

        Usa el código específico ``WEIGHT_MUST_BE_KILOGRAM_NUMBER`` igual
        que en el registro, para que la UI reutilice el mismo mensaje.

        Args:
            v: valor crudo.
            handler: validador original.

        Returns:
            Número ya validado si pasa.

        Raises:
            AppValidationError: ``WEIGHT_MUST_BE_KILOGRAM_NUMBER`` si no es numérico.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "WEIGHT_MUST_BE_KILOGRAM_NUMBER",
            "Error: El peso debe ser un número en kilos",
        )

    @field_validator("peso")
    @classmethod
    def validar_peso_actualizacion(cls, v):
        """Aplica el rango humano razonable al peso en el PATCH.

        Delega en ``validators.validar_peso_logica`` (admite ``None``).

        Args:
            v: peso en kilogramos, o ``None``.

        Returns:
            El mismo valor si pasa.

        Raises:
            AppValidationError: ``WEIGHT_OUT_OF_RANGE`` si no está en [20, 300].
        """
        return validators.validar_peso_logica(v)

    @field_validator("provincia", mode="wrap")
    @classmethod
    def validar_provincia_actualizacion_custom(cls, v, handler):
        """Intercepta errores de parseo del enum ``ProvinciaEspaña`` en PATCH.

        Mismo tratamiento que en el registro para que los mensajes sean
        consistentes.

        Args:
            v: valor crudo.
            handler: validador original del enum.

        Returns:
            Valor ya validado por el enum si pasa.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si no pertenece al enum.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La ubicación seleccionada no es válida",
        )

    @field_validator("perfil_visible", mode="wrap")
    @classmethod
    def validar_perfil_visible_actualizacion_custom(cls, v, handler):
        """Intercepta errores de parseo del booleano ``perfil_visible`` en PATCH.

        Equivalente a la versión de ``Registro``.

        Args:
            v: valor crudo.
            handler: validador original.

        Returns:
            Booleano ya validado si pasa.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si no se puede interpretar como booleano.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: El formato de perfil visible no es válido",
        )

    @field_validator("objetivo_semanal_metros")
    @classmethod
    def validar_objetivo_semanal(cls, v: Optional[int]) -> Optional[int]:
        """Valida el objetivo semanal en metros dentro de un rango razonable.

        Admite ``None`` (no cambiar). Si hay valor, exige entero estricto
        (no float, usando ``isinstance(v, int)``) y un rango amplio (10 m a
        2 000 000 m) que cubre desde objetivos muy modestos hasta los de un
        corredor de ultrafondo, sin admitir valores absurdos que indicarían
        un cliente roto.

        Args:
            v: objetivo en metros o ``None``.

        Returns:
            El mismo valor si pasa; ``None`` si no se cambia.

        Raises:
            AppValidationError: ``WEEKLY_GOAL_MUST_BE_INTEGER_METERS`` si no es entero.
            AppValidationError: ``WEEKLY_GOAL_OUT_OF_RANGE`` si está fuera de [10, 2 000 000].
        """
        if v is None:
            return v
        if not isinstance(v, int):
            raise AppValidationError(
                "Error: El objetivo semanal debe ser un número entero en metros",
                "WEEKLY_GOAL_MUST_BE_INTEGER_METERS",
            )
        if not (10 <= v <= 2_000_000):
            raise AppValidationError(
                "Error: El objetivo semanal debe estar entre 10 y 2 000 000 metros",
                "WEEKLY_GOAL_OUT_OF_RANGE",
            )
        return v

    @field_validator("objetivo_mensual_metros")
    @classmethod
    def validar_objetivo_mensual(cls, v: Optional[int]) -> Optional[int]:
        """Valida el objetivo mensual en metros dentro del mismo rango que el semanal.

        Se permite deliberadamente que el mensual y el semanal usen el
        mismo rango numérico (10 m a 2 000 000 m). El servicio no obliga a
        que ``mensual >= semanal × 4``: algunos usuarios quieren marcarse
        un objetivo mensual más holgado y dividir a su ritmo.

        Args:
            v: objetivo en metros o ``None``.

        Returns:
            El mismo valor si pasa; ``None`` si no se cambia.

        Raises:
            AppValidationError: ``MONTHLY_GOAL_MUST_BE_INTEGER_METERS`` si no es entero.
            AppValidationError: ``MONTHLY_GOAL_OUT_OF_RANGE`` si está fuera de [10, 2 000 000].
        """
        if v is None:
            return v
        if not isinstance(v, int):
            raise AppValidationError(
                "Error: El objetivo mensual debe ser un número entero en metros",
                "MONTHLY_GOAL_MUST_BE_INTEGER_METERS",
            )
        if not (10 <= v <= 2_000_000):
            raise AppValidationError(
                "Error: El objetivo mensual debe estar entre 10 y 2 000 000 metros",
                "MONTHLY_GOAL_OUT_OF_RANGE",
            )
        return v


class InformacionPerfilPublico(BaseModel):
    """
    Esquema reducido para ver el perfil de otro usuario.
    Oculta datos sensibles (email, peso, fecha nacimiento, etc).
    """

    nombre_usuario: str
    provincia: Optional[str] = None
    foto_perfil: Optional[str] = None
    foto_version: int = 0
    total_puntos: int


class BusquedaUsuario(BaseModel):
    """
    Esquema para resultados de la barra de búsqueda.
    """

    nombre_usuario: str
    foto_perfil: Optional[str] = None
    foto_version: int = 0


class RespuestaBusquedaUsuariosPaginada(BaseModel):
    """
    Esquema para resultados paginados de la barra de búsqueda.
    """

    items: List[BusquedaUsuario]
    total: int
    skip: int
    limit: int
    has_more: bool


class ReportePerfilInapropiado(BaseModel):
    """Representa reporte perfil inapropiado."""

    nombre_usuario_reportado: str = Field(..., min_length=1, max_length=50)
    reportar_nombre: bool = False
    reportar_foto: bool = False
    observaciones: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def validar_campos_requeridos(cls, values: Any) -> Any:
        """Comprueba presencia del ``nombre_usuario_reportado``.

        Las banderas ``reportar_nombre`` / ``reportar_foto`` se validan en
        otro validator (``validar_motivos``) con su propio mensaje: aquí
        solo se asegura que sepamos a quién se reporta.

        Args:
            values: diccionario crudo de entrada.

        Returns:
            El mismo ``values`` si el obligatorio está presente.

        Raises:
            AppValidationError: ``REPORT_TARGET_USERNAME_REQUIRED`` si falta el nombre del reportado.
        """
        if isinstance(values, dict):
            if (
                "nombre_usuario_reportado" not in values
                or values["nombre_usuario_reportado"] is None
            ):
                raise AppValidationError(
                    "Error: El nombre de usuario reportado es obligatorio",
                    "REPORT_TARGET_USERNAME_REQUIRED",
                )
        return values

    @field_validator("nombre_usuario_reportado", mode="before")
    @classmethod
    def limpiar_nombre_usuario_reportado(cls, valor: Any) -> Any:
        """Recorta el nombre reportado y rechaza cadenas vacías tras el recorte.

        La búsqueda posterior compara case-insensitive en ``user_service``,
        así que no se fuerza el caso aquí para no perder el original en
        caso de auditoría posterior.

        Args:
            valor: nombre del usuario reportado tal como llega del cliente.

        Returns:
            Nombre recortado si es cadena; el valor crudo si no lo es.

        Raises:
            AppValidationError: ``REPORT_TARGET_USERNAME_EMPTY`` si tras recortar queda vacío.
        """
        if isinstance(valor, str):
            valor_limpio = valor.strip()
            if not valor_limpio:
                raise AppValidationError(
                    "Error: El nombre de usuario reportado no puede estar vacío",
                    "REPORT_TARGET_USERNAME_EMPTY",
                )
            return valor_limpio
        return valor

    @field_validator("observaciones", mode="before")
    @classmethod
    def limpiar_observaciones(cls, valor: Any) -> Any:
        """Recorta las observaciones y colapsa cadenas vacías a ``None``.

        Una cadena con solo espacios no aporta nada al moderador; guardarla
        llenaría la base de basura. Colapsar a ``None`` permite además que
        la plantilla de email muestre "Sin observaciones" de forma uniforme.

        Args:
            valor: observaciones opcionales del reportante.

        Returns:
            Observaciones recortadas si aportan contenido; ``None`` si eran vacías o solo espacios.
        """
        if valor is None:
            return None
        if isinstance(valor, str):
            valor_limpio = valor.strip()
            return valor_limpio or None
        return valor

    @model_validator(mode="after")
    def validar_motivos(self):
        """Exige al menos un motivo marcado entre ``reportar_nombre`` y ``reportar_foto``.

        El formulario tiene dos checkboxes; si ambos llegan en ``False`` no
        hay nada que reportar y dejar pasar el request solo generaría
        ruido en el buzón de moderación. Se valida en ``mode='after'`` para
        poder leer ambos campos ya parseados por Pydantic.

        Returns:
            La propia instancia si al menos un motivo está marcado.

        Raises:
            AppValidationError: ``AT_LEAST_ONE_REPORT_REASON_REQUIRED`` si los dos motivos son ``False``.
        """
        if not self.reportar_nombre and not self.reportar_foto:
            raise AppValidationError(
                "Error: Debes marcar al menos una opción de reporte",
                "AT_LEAST_ONE_REPORT_REASON_REQUIRED",
            )
        return self


class SolicitarPassword(BaseModel):
    """Esquema para solicitar recuperación indicando el idioma del correo."""

    email: EmailStr
    locale: str

    @model_validator(mode="before")
    @classmethod
    def validar_campos_requeridos_solicitar_recuperacion(cls, values: Any) -> Any:
        """Comprueba presencia explícita de ``email`` y ``locale``.

        El ``locale`` es obligatorio porque decide el idioma del correo
        que se enviará al usuario; sin él no se puede renderizar la plantilla.

        Args:
            values: diccionario crudo de entrada.

        Returns:
            El mismo ``values`` si todos los obligatorios están presentes.

        Raises:
            AppValidationError: ``EMAIL_REQUIRED`` o ``LOCALE_REQUIRED`` según qué falte.
        """
        if isinstance(values, dict):
            if "email" not in values or not values["email"]:
                raise AppValidationError(
                    "Error: El email es obligatorio", "EMAIL_REQUIRED"
                )
            if "locale" not in values or not values["locale"]:
                raise AppValidationError(
                    "Error: El idioma es obligatorio", "LOCALE_REQUIRED"
                )
        return values

    @field_validator("email", mode="before")
    @classmethod
    def validar_email_solicitar_recuperacion(cls, valor: Any) -> Any:
        """Normaliza el email a minúsculas antes de pasar a ``EmailStr``.

        Mismo motivo que en los demás esquemas: homogeneizar la clave de
        búsqueda y evitar duplicados espurios.

        Args:
            valor: valor crudo del campo ``email``.

        Returns:
            Cadena en minúsculas recortada, o el valor tal cual si no es cadena.
        """
        if isinstance(valor, str):
            return valor.lower().strip()
        return valor

    @field_validator("email", mode="wrap")
    @classmethod
    def validar_email_solicitar_recuperacion_custom(cls, v, handler):
        """Sustituye el error de ``EmailStr`` por ``EMAIL_FORMAT_INVALID``.

        Mismo patrón que en el registro: traduce el mensaje técnico de
        Pydantic a un código canónico que la UI entiende.

        Args:
            v: valor a validar.
            handler: validador original de ``EmailStr``.

        Returns:
            Email ya validado si pasa.

        Raises:
            AppValidationError: ``EMAIL_FORMAT_INVALID`` si el formato no es válido.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "EMAIL_FORMAT_INVALID",
            "Error: El formato del correo electrónico no es válido",
        )

    @field_validator("locale", mode="before")
    @classmethod
    def validar_locale_solicitar_recuperacion(cls, valor: Any) -> str:
        """Normaliza el ``locale`` al conjunto cerrado ``{"es", "en"}``.

        Acepta cualquier variante (``es``, ``es-ES``, ``es_ES``, ``en``,
        ``en-US``...) y reduce a ``"es"`` o ``"en"`` según el prefijo. Si
        llega algo fuera de esos dos prefijos, se rechaza con
        ``LOCALE_NOT_SUPPORTED`` en lugar de caer silenciosamente al
        default, para que el cliente sepa que la app le envió algo
        inesperado.

        Args:
            valor: locale tal como llega del cliente.

        Returns:
            ``"es"`` si empieza por español, ``"en"`` si empieza por inglés.

        Raises:
            AppValidationError: ``LOCALE_MUST_BE_TEXT`` si no es cadena.
            AppValidationError: ``LOCALE_REQUIRED`` si queda vacío tras normalizar.
            AppValidationError: ``LOCALE_NOT_SUPPORTED`` si el prefijo no coincide con ``es``/``en``.
        """
        # Valida configuración regional solicitar recuperacion.
        if not isinstance(valor, str):
            raise AppValidationError(
                "Error: El idioma debe ser un texto", "LOCALE_MUST_BE_TEXT"
            )

        locale = valor.strip().lower().replace("_", "-")
        if not locale:
            raise AppValidationError(
                "Error: El idioma es obligatorio", "LOCALE_REQUIRED"
            )
        if locale.startswith("es"):
            return "es"
        if locale.startswith("en"):
            return "en"

        raise AppValidationError(
            "Error: El idioma no es compatible", "LOCALE_NOT_SUPPORTED"
        )


class ConfirmarPassword(BaseModel):
    """Esquema para cambiar la contraseña usando el código recibido."""

    email: EmailStr
    codigo: str = Field(...)
    nueva_password: str

    @model_validator(mode="before")
    @classmethod
    def validar_campos_confirmar_recuperacion(cls, values: Any) -> Any:
        """Comprueba presencia de los tres obligatorios (email, código, nueva contraseña).

        Mismo patrón que los demás pre-validadores. Cada ausencia produce
        un código distinto (``EMAIL_REQUIRED``, ``CODE_REQUIRED``,
        ``NEW_PASSWORD_REQUIRED``) para que el cliente resalte el campo exacto.

        Args:
            values: diccionario crudo de entrada.

        Returns:
            El mismo ``values`` si todos los obligatorios están presentes.

        Raises:
            AppValidationError: ``EMAIL_REQUIRED``, ``CODE_REQUIRED`` o ``NEW_PASSWORD_REQUIRED`` según qué falte.
        """
        # Valida campos confirmar recuperacion.
        if isinstance(values, dict):
            if "email" not in values or not values["email"]:
                raise AppValidationError(
                    "Error: El email es obligatorio", "EMAIL_REQUIRED"
                )
            if "codigo" not in values or not values["codigo"]:
                raise AppValidationError(
                    "Error: El código es obligatorio", "CODE_REQUIRED"
                )
            if "nueva_password" not in values or not values["nueva_password"]:
                raise AppValidationError(
                    "Error: La nueva contraseña es obligatoria", "NEW_PASSWORD_REQUIRED"
                )
        return values

    @field_validator("nueva_password")
    @classmethod
    def validar_nueva_password_confirmar_recuperacion(cls, v):
        """Aplica la política de contraseñas a la nueva contraseña del reseteo.

        Delega en ``validators.validar_password_logica`` con los mismos
        requisitos que en alta y actualización: 8–72 bytes, mayúscula y dígito.

        Args:
            v: nueva contraseña en claro.

        Returns:
            La misma contraseña si pasa todas las comprobaciones.

        Raises:
            AppValidationError: ``PASSWORD_TOO_SHORT``, ``PASSWORD_TOO_LONG_BYTES``, ``PASSWORD_MISSING_UPPERCASE`` o ``PASSWORD_MISSING_NUMBER``.
        """
        return validators.validar_password_logica(v)

    @field_validator("codigo", mode="before")
    @classmethod
    def limpiar_codigo_confirmar_recuperacion(cls, v) -> Any:
        """Recorta el código y valida que sean exactamente 6 dígitos.

        El código que genera ``access_service.generar_codigo_recuperacion``
        siempre es de 6 dígitos, así que aquí rechazamos en el esquema
        cualquier cosa que no pueda ser válida, sin hacer IO a la base para
        comparar un hash que ya sabemos que no va a coincidir.

        Args:
            v: código tal como llega del cliente.

        Returns:
            Código recortado si pasa las comprobaciones; el valor crudo si no es cadena.

        Raises:
            AppValidationError: ``CODE_EMPTY`` si queda vacío tras recortar.
            AppValidationError: ``CODE_INVALID_LENGTH`` si la longitud no es 6.
            AppValidationError: ``CODE_MUST_BE_NUMERIC`` si contiene caracteres no numéricos.
        """
        if isinstance(v, str):
            # Quitar espacios delante y detrás.
            valor_limpio = v.strip()
            if not valor_limpio:
                raise AppValidationError(
                    "Error: El código no puede estar vacío", "CODE_EMPTY"
                )
            if len(valor_limpio) != 6:
                raise AppValidationError(
                    "Error: El código debe tener exactamente 6 caracteres",
                    "CODE_INVALID_LENGTH",
                )
            if not valor_limpio.isdigit():
                raise AppValidationError(
                    "Error: El código debe contener solo números",
                    "CODE_MUST_BE_NUMERIC",
                )
            return valor_limpio
        return v

    @field_validator("email", mode="before")
    @classmethod
    def validar_email_confirmar_recuperacion(cls, valor: Any) -> Any:
        """Normaliza el email a minúsculas antes de pasar a ``EmailStr``.

        Mismo motivo que en el resto de esquemas: mantener la forma
        canónica que se usa como clave de búsqueda en base de datos.

        Args:
            valor: valor crudo del campo ``email``.

        Returns:
            Cadena en minúsculas recortada, o el valor tal cual si no es cadena.
        """
        if isinstance(valor, str):
            return valor.lower().strip()
        return valor

    @field_validator("email", mode="wrap")
    @classmethod
    def validar_email_confirmar_recuperacion_custom(cls, v, handler):
        """Sustituye el error de ``EmailStr`` por ``EMAIL_FORMAT_INVALID``.

        Equivalente al wrapper de los demás esquemas que usan ``EmailStr``.

        Args:
            v: valor a validar.
            handler: validador original de ``EmailStr``.

        Returns:
            Email ya validado si pasa.

        Raises:
            AppValidationError: ``EMAIL_FORMAT_INVALID`` si el formato no es válido.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "EMAIL_FORMAT_INVALID",
            "Error: El formato del correo electrónico no es válido",
        )


class GuardarActividad(BaseModel):
    """Payload validado para persistir una actividad con métricas enriquecidas."""

    client_local_id: Optional[str] = Field(None, max_length=64)
    tipo: TipoActividad
    distancia: StrictInt = Field(...)
    duracion_total: StrictInt = Field(...)
    duracion_movimiento: StrictInt = Field(...)
    duracion_parado: StrictInt = Field(default=0)
    duracion_pausa_manual: StrictInt = Field(default=0)
    calorias_quemadas: StrictInt = Field(...)
    pasos: Optional[StrictInt] = Field(default=None)
    ritmo_medio_movimiento: StrictInt = Field(default=0)
    ritmo_medio_total: StrictInt = Field(default=0)
    ritmo_maximo: StrictInt = Field(default=0)
    velocidad_media_x100: StrictInt = Field(default=0)
    velocidad_max_x100: StrictInt = Field(default=0)
    auto_pausas: StrictInt = Field(default=0)
    pausas_manuales: StrictInt = Field(default=0)
    alertas_velocidad: StrictInt = Field(default=0)
    ruta_polilinea: Optional[str] = Field(None, max_length=200000)
    ruta_mapa_url: Optional[AnyHttpUrl] = Field(None, max_length=2048)
    fecha_ruta: datetime

    @model_validator(mode="before")
    @classmethod
    def validar_campos_requeridos_actividad(cls, values: Any) -> Any:
        """Comprueba presencia de todos los campos obligatorios de actividad.

        Teniendo tantos campos obligatorios (``tipo``, ``distancia``,
        ``duracion_total``, ``duracion_movimiento``, ``calorias_quemadas``,
        ``fecha_ruta``), este pre-validador recorre un diccionario
        ``{campo: (mensaje, error_code)}`` en lugar de hacer ``if`` anidados.
        Cada ausencia sigue produciendo su propio código canónico para que
        el cliente Android pueda mapear error a UI sin parsear mensajes.

        Args:
            values: diccionario crudo de entrada.

        Returns:
            El mismo ``values`` si todos los obligatorios están presentes.

        Raises:
            AppValidationError: códigos ``ACTIVITY_TYPE_REQUIRED``, ``DISTANCE_REQUIRED``, ``TOTAL_DURATION_REQUIRED``, ``MOVING_DURATION_REQUIRED``, ``BURNED_CALORIES_REQUIRED`` o ``ACTIVITY_DATE_REQUIRED`` según qué falte.
        """
        # Valida campos requeridos actividad.
        if isinstance(values, dict):
            required_fields = {
                "tipo": (
                    "Error: El tipo de actividad es obligatorio",
                    "ACTIVITY_TYPE_REQUIRED",
                ),
                "distancia": (
                    "Error: La distancia es obligatoria",
                    "DISTANCE_REQUIRED",
                ),
                "duracion_total": (
                    "Error: La duración total es obligatoria",
                    "TOTAL_DURATION_REQUIRED",
                ),
                "duracion_movimiento": (
                    "Error: La duración en movimiento es obligatoria",
                    "MOVING_DURATION_REQUIRED",
                ),
                "calorias_quemadas": (
                    "Error: Las calorías quemadas son obligatorias",
                    "BURNED_CALORIES_REQUIRED",
                ),
                "fecha_ruta": (
                    "Error: La fecha de la actividad es obligatoria",
                    "ACTIVITY_DATE_REQUIRED",
                ),
            }
            for field_name, (message, code) in required_fields.items():
                if field_name not in values:
                    raise AppValidationError(message, code)
        return values

    @field_validator("client_local_id")
    @classmethod
    def validar_client_local_id_actividad(cls, v):
        """Valida el identificador local opcional para idempotencia de subidas.

        Este id lo genera la app Android al crear la actividad y lo reenvía
        en el POST para que el backend pueda detectar reintentos y
        responder la actividad ya persistida en lugar de crear duplicados.
        Admite ``None`` (cliente antiguo que no lo envía) pero si se envía:

        - Tiene que ser cadena no vacía tras recortar.
        - No puede superar 64 caracteres (suficiente para UUIDs).

        Args:
            v: id local o ``None``.

        Returns:
            Id recortado, o ``None`` si venía ``None``.

        Raises:
            AppValidationError: ``ACTIVITY_CLIENT_LOCAL_ID_INVALID`` si no es cadena o queda vacío.
            AppValidationError: ``ACTIVITY_CLIENT_LOCAL_ID_TOO_LONG`` si supera 64 caracteres.
        """
        if v is None:
            return None
        if not isinstance(v, str):
            raise AppValidationError(
                "Error: El identificador local de la actividad debe ser texto",
                "ACTIVITY_CLIENT_LOCAL_ID_INVALID",
            )
        v = v.strip()
        if not v:
            raise AppValidationError(
                "Error: El identificador local de la actividad no puede estar vacío",
                "ACTIVITY_CLIENT_LOCAL_ID_INVALID",
            )
        if len(v) > 64:
            raise AppValidationError(
                "Error: El identificador local de la actividad no puede superar los 64 caracteres",
                "ACTIVITY_CLIENT_LOCAL_ID_TOO_LONG",
            )
        return v

    @field_validator("tipo", mode="wrap")
    @classmethod
    def validar_tipo_actividad_custom(cls, v, handler):
        """Intercepta errores de parseo del enum ``TipoActividad``.

        El enum tiene un conjunto cerrado (correr, caminar...); si el cliente
        envía algo fuera de él, Pydantic soltaría un error técnico. Aquí
        se traduce a ``VALIDATION_ERROR`` con mensaje en español.

        Args:
            v: valor crudo.
            handler: validador original del enum.

        Returns:
            Valor ya validado por el enum si pasa.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si no pertenece al enum.
        """
        return validators.interceptar_error_pydantic(
            v, handler, "VALIDATION_ERROR", "Error: El tipo de actividad no es válido"
        )

    @field_validator("distancia", mode="wrap")
    @classmethod
    def validar_distancia_actividad_custom(cls, v, handler):
        """Intercepta errores de tipo al parsear ``distancia`` como entero estricto.

        La distancia se envía como ``StrictInt`` en metros para evitar
        ambigüedades de float. Si llega en otro formato, aquí se traduce
        el error a un mensaje humano.

        Args:
            v: valor crudo del campo ``distancia``.
            handler: validador original.

        Returns:
            Entero ya validado si pasa.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si el valor no es entero.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: La distancia debe ser un número válido en metros",
        )

    @field_validator("distancia")
    @classmethod
    def validar_distancia_actividad(cls, v):
        """Aplica el rango operativo de la distancia (>0 y <=300 km).

        Delega en ``validators.validar_distancia_logica``. El tope es una
        sanity check (nadie corre más de 300 km en una sesión única) y
        funciona como cortafuegos ante clientes rotos que podrían enviar
        valores absurdos.

        Args:
            v: distancia en metros.

        Returns:
            El mismo valor si pasa el rango.

        Raises:
            AppValidationError: ``DISTANCE_MUST_BE_POSITIVE`` si ``v <= 0``.
            AppValidationError: ``DISTANCE_OUT_OF_RANGE`` si supera 300 000 m.
        """
        return validators.validar_distancia_logica(v)

    @field_validator(
        "duracion_total",
        "duracion_movimiento",
        "duracion_parado",
        "duracion_pausa_manual",
        mode="wrap",
    )
    @classmethod
    def validar_duraciones_custom(cls, v, handler):
        """Intercepta errores de tipo en las 4 duraciones (``StrictInt``).

        Se aplica al bloque ``duracion_total``, ``duracion_movimiento``,
        ``duracion_parado``, ``duracion_pausa_manual`` en una única definición
        para no duplicar el wrapper por cada campo.

        Args:
            v: valor crudo del campo.
            handler: validador original de enteros.

        Returns:
            Entero ya validado si pasa.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si el valor no es entero.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: Las duraciones deben ser números enteros en segundos",
        )

    @field_validator("duracion_total")
    @classmethod
    def validar_duracion_total(cls, v):
        """Aplica el rango operativo (>0 y <=24h) a la duración total.

        Delega en ``validators.validar_duracion_logica``. La duración total
        es obligatoria y debe ser positiva: una actividad sin tiempo
        registrado no tiene sentido.

        Args:
            v: duración total en segundos.

        Returns:
            El mismo valor si pasa el rango.

        Raises:
            AppValidationError: ``DURATION_MUST_BE_POSITIVE`` si ``v <= 0``.
            AppValidationError: ``DURATION_TOO_LONG`` si supera 86 400 s.
        """
        return validators.validar_duracion_logica(v)

    @field_validator("duracion_movimiento")
    @classmethod
    def validar_duracion_movimiento(cls, v):
        """Aplica el mismo rango operativo a la duración en movimiento.

        Mismo validador que ``duracion_total``. El validador a nivel de
        modelo (``validar_consistencia_temporal``) garantiza además que
        ``duracion_movimiento <= duracion_total``.

        Args:
            v: duración en movimiento en segundos.

        Returns:
            El mismo valor si pasa el rango.

        Raises:
            AppValidationError: ``DURATION_MUST_BE_POSITIVE`` o ``DURATION_TOO_LONG``.
        """
        return validators.validar_duracion_logica(v)

    @field_validator("duracion_parado")
    @classmethod
    def validar_duracion_parado(cls, v):
        """Permite que la duración parada sea cero, con tope de 24 horas.

        Delega en ``validators.validar_duracion_no_negativa_logica``, que
        contrasta con ``validar_duracion_logica`` en que admite ``0``:
        una actividad sin ningún período parado es perfectamente legítima.

        Args:
            v: duración parada en segundos.

        Returns:
            El mismo valor si pasa el rango.

        Raises:
            AppValidationError: ``STOPPED_DURATION_NEGATIVE`` o ``STOPPED_DURATION_TOO_LONG``.
        """
        return validators.validar_duracion_no_negativa_logica(
            v, "la duración parada", "STOPPED_DURATION"
        )

    @field_validator("duracion_pausa_manual")
    @classmethod
    def validar_duracion_pausa_manual(cls, v):
        """Permite que la pausa manual sea cero, con tope de 24 horas.

        Idéntica semántica a ``validar_duracion_parado`` pero con prefijo
        de error propio para distinguir en logs/UI.

        Args:
            v: duración de pausa manual en segundos.

        Returns:
            El mismo valor si pasa el rango.

        Raises:
            AppValidationError: ``MANUAL_PAUSE_DURATION_NEGATIVE`` o ``MANUAL_PAUSE_DURATION_TOO_LONG``.
        """
        return validators.validar_duracion_no_negativa_logica(
            v, "la duración de pausa manual", "MANUAL_PAUSE_DURATION"
        )

    @field_validator("calorias_quemadas", mode="wrap")
    @classmethod
    def validar_calorias_actividad_custom(cls, v, handler):
        """Intercepta errores de tipo al parsear ``calorias_quemadas`` como entero.

        Usa el código específico ``CALORIES_MUST_BE_INTEGER`` (no el
        genérico ``VALIDATION_ERROR``) para que la UI pueda mostrar un
        mensaje concreto.

        Args:
            v: valor crudo.
            handler: validador original de enteros.

        Returns:
            Entero ya validado si pasa.

        Raises:
            AppValidationError: ``CALORIES_MUST_BE_INTEGER`` si no es entero.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "CALORIES_MUST_BE_INTEGER",
            "Error: Las calorías deben ser un número entero",
        )

    @field_validator("calorias_quemadas")
    @classmethod
    def validar_calorias_actividad(cls, v):
        """Aplica el rango fisiológico (>0 y <=10000) a las calorías.

        Delega en ``validators.validar_calorias_logica``. Quemar más de
        10 000 calorías en una sesión es fisiológicamente improbable;
        rechazarlo filtra inputs claramente rotos.

        Args:
            v: calorías quemadas.

        Returns:
            El mismo valor si pasa el rango.

        Raises:
            AppValidationError: ``CALORIES_MUST_BE_POSITIVE`` o ``CALORIES_OUT_OF_RANGE``.
        """
        return validators.validar_calorias_logica(v)

    @field_validator("pasos", mode="wrap")
    @classmethod
    def validar_pasos_custom(cls, v, handler):
        """Traduce a un error canónico los conteos de pasos que no sean enteros."""
        if v is None:
            return None
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "STEPS_MUST_BE_INTEGER",
            "Error: Los pasos deben ser un número entero",
        )

    @field_validator("pasos")
    @classmethod
    def validar_pasos(cls, v):
        """Acepta ``None`` para dispositivos sin sensor y limita conteos corruptos."""
        if v is None:
            return None
        if v < 0:
            raise AppValidationError(
                "Error: Los pasos no pueden ser negativos", "STEPS_NEGATIVE"
            )
        if v > 500000:
            raise AppValidationError(
                "Error: El número de pasos está fuera de rango",
                "STEPS_OUT_OF_RANGE",
            )
        return v

    @field_validator("ritmo_medio_movimiento", "ritmo_medio_total", mode="wrap")
    @classmethod
    def validar_ritmos_custom(cls, v, handler):
        """Intercepta errores de tipo en los ritmos (``ritmo_medio_movimiento``, ``ritmo_medio_total``).

        Se aplica a ambos campos en una única definición para no duplicar
        el wrapper.

        Args:
            v: valor crudo.
            handler: validador original de enteros.

        Returns:
            Entero ya validado si pasa.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si el valor no es entero.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: Los ritmos deben ser enteros en segundos por kilómetro",
        )

    @field_validator("ritmo_medio_movimiento")
    @classmethod
    def validar_ritmo_medio_movimiento(cls, v):
        """Valida el ritmo medio en movimiento (0–3600 s/km).

        Delega en ``validators.validar_ritmo_segundos_km_logica`` con el
        prefijo ``MOVING_PACE``.

        Args:
            v: ritmo en segundos por kilómetro.

        Returns:
            El mismo valor si pasa el rango.

        Raises:
            AppValidationError: ``MOVING_PACE_NEGATIVE`` o ``MOVING_PACE_OUT_OF_RANGE``.
        """
        return validators.validar_ritmo_segundos_km_logica(
            v, "el ritmo medio en movimiento", "MOVING_PACE"
        )

    @field_validator("ritmo_medio_total")
    @classmethod
    def validar_ritmo_medio_total(cls, v):
        """Valida el ritmo medio total (0–3600 s/km).

        Mismo rango que el de movimiento, con prefijo ``TOTAL_PACE`` para
        distinguir en errores.

        Args:
            v: ritmo en segundos por kilómetro.

        Returns:
            El mismo valor si pasa el rango.

        Raises:
            AppValidationError: ``TOTAL_PACE_NEGATIVE`` o ``TOTAL_PACE_OUT_OF_RANGE``.
        """
        return validators.validar_ritmo_segundos_km_logica(
            v, "el ritmo medio total", "TOTAL_PACE"
        )

    @field_validator("velocidad_media_x100", "velocidad_max_x100", mode="wrap")
    @classmethod
    def validar_velocidades_custom(cls, v, handler):
        """Intercepta errores de tipo en ``velocidad_media_x100`` y ``velocidad_max_x100``.

        Las velocidades se envían como enteros ``km/h × 100`` para no usar
        floats; este wrapper solo traduce el error de tipo.

        Args:
            v: valor crudo.
            handler: validador original.

        Returns:
            Entero ya validado si pasa.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si no es entero.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: Las velocidades deben ser enteros en km/h x100",
        )

    @field_validator("velocidad_media_x100")
    @classmethod
    def validar_velocidad_media(cls, v):
        """Valida la velocidad media en rango 0–10 000 (= 0–100 km/h).

        Delega en ``validators.validar_velocidad_x100_logica`` con prefijo
        ``AVERAGE_SPEED``.

        Args:
            v: velocidad media expresada como km/h × 100.

        Returns:
            El mismo valor si pasa el rango.

        Raises:
            AppValidationError: ``AVERAGE_SPEED_NEGATIVE`` o ``AVERAGE_SPEED_OUT_OF_RANGE``.
        """
        return validators.validar_velocidad_x100_logica(
            v, "la velocidad media", "AVERAGE_SPEED"
        )

    @field_validator("velocidad_max_x100")
    @classmethod
    def validar_velocidad_max(cls, v):
        """Valida la velocidad máxima en rango 0–10 000 (= 0–100 km/h).

        Mismo rango que la media. La consistencia ``máxima >= media`` se
        garantiza en el validador a nivel de modelo ``validar_consistencia_temporal``.

        Args:
            v: velocidad máxima expresada como km/h × 100.

        Returns:
            El mismo valor si pasa el rango.

        Raises:
            AppValidationError: ``MAX_SPEED_NEGATIVE`` o ``MAX_SPEED_OUT_OF_RANGE``.
        """
        return validators.validar_velocidad_x100_logica(
            v, "la velocidad máxima", "MAX_SPEED"
        )

    @field_validator("auto_pausas", "pausas_manuales", "alertas_velocidad", mode="wrap")
    @classmethod
    def validar_contadores_custom(cls, v, handler):
        """Intercepta errores de tipo en los tres contadores del tracking.

        Aplica a ``auto_pausas``, ``pausas_manuales`` y ``alertas_velocidad``
        en una definición única.

        Args:
            v: valor crudo.
            handler: validador original.

        Returns:
            Entero ya validado si pasa.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si no es entero.
        """
        return validators.interceptar_error_pydantic(
            v,
            handler,
            "VALIDATION_ERROR",
            "Error: Los contadores deben ser enteros no negativos",
        )

    @field_validator("auto_pausas")
    @classmethod
    def validar_auto_pausas(cls, v):
        """Valida el contador de auto-pausas (0–500).

        Delega en ``validators.validar_contador_tracking_logica`` con prefijo
        ``AUTO_PAUSE_COUNT``. El tope de 500 descarta inputs claramente
        rotos sin invalidar sesiones largas reales.

        Args:
            v: número de auto-pausas detectadas.

        Returns:
            El mismo valor si pasa el rango.

        Raises:
            AppValidationError: ``AUTO_PAUSE_COUNT_NEGATIVE`` o ``AUTO_PAUSE_COUNT_OUT_OF_RANGE``.
        """
        return validators.validar_contador_tracking_logica(
            v, "las auto pausas", "AUTO_PAUSE_COUNT"
        )

    @field_validator("pausas_manuales")
    @classmethod
    def validar_pausas_manuales(cls, v):
        """Valida el contador de pausas manuales (0–500).

        Mismo rango y mismo validador que las auto-pausas, con prefijo
        ``MANUAL_PAUSE_COUNT``.

        Args:
            v: número de pausas manuales.

        Returns:
            El mismo valor si pasa el rango.

        Raises:
            AppValidationError: ``MANUAL_PAUSE_COUNT_NEGATIVE`` o ``MANUAL_PAUSE_COUNT_OUT_OF_RANGE``.
        """
        return validators.validar_contador_tracking_logica(
            v, "las pausas manuales", "MANUAL_PAUSE_COUNT"
        )

    @field_validator("alertas_velocidad")
    @classmethod
    def validar_alertas_velocidad(cls, v):
        """Valida el contador de alertas de velocidad (0–500).

        Mismo rango que el resto de contadores, con prefijo
        ``SPEED_ALERT_COUNT``.

        Args:
            v: número de alertas de velocidad disparadas durante la sesión.

        Returns:
            El mismo valor si pasa el rango.

        Raises:
            AppValidationError: ``SPEED_ALERT_COUNT_NEGATIVE`` o ``SPEED_ALERT_COUNT_OUT_OF_RANGE``.
        """
        return validators.validar_contador_tracking_logica(
            v, "las alertas de velocidad", "SPEED_ALERT_COUNT"
        )

    @field_validator("fecha_ruta", mode="wrap")
    @classmethod
    def validar_fecha_ruta_actividad_custom(cls, v, handler):
        """Intercepta errores de parseo de ``fecha_ruta`` (datetime con zona).

        El formato esperado es ISO-8601 con offset; si el cliente envía
        otra cosa, aquí se traduce el error de Pydantic a un mensaje
        humano con ``VALIDATION_ERROR``.

        Args:
            v: valor crudo del campo ``fecha_ruta``.
            handler: validador original.

        Returns:
            ``datetime`` ya parseado si el formato es válido.

        Raises:
            AppValidationError: ``VALIDATION_ERROR`` si el formato no es parseable.
        """
        return validators.interceptar_error_pydantic(
            v, handler, "VALIDATION_ERROR", "Error: El formato de fecha no es válido"
        )

    @field_validator("fecha_ruta")
    @classmethod
    def validar_fecha_ruta_actividad(cls, v):
        """Exige zona horaria, rechaza futuro y normaliza a UTC.

        Delega en ``validators.validar_fecha_ruta_logica``, que admite
        hasta 10 minutos en el futuro para absorber desajustes de reloj
        entre dispositivo y servidor y normaliza a UTC para que la base
        de datos guarde siempre valores homogéneos.

        Args:
            v: ``datetime`` ya parseado.

        Returns:
            El mismo instante normalizado a UTC.

        Raises:
            AppValidationError: ``ACTIVITY_DATE_MISSING_TIMEZONE`` si falta ``tzinfo``.
            AppValidationError: ``ACTIVITY_DATE_IN_FUTURE`` si supera ``ahora + 10 minutos``.
        """
        return validators.validar_fecha_ruta_logica(v)

    @field_validator("ruta_polilinea", mode="before")
    @classmethod
    def validar_polilinea_actividad(cls, v):
        """Normaliza cadena vacía a ``None`` y valida el tamaño de la polilínea.

        Admite que el cliente envíe ``""`` como equivalente a "sin ruta"
        (p. ej. tracking GPS deshabilitado) colapsándolo a ``None`` aquí,
        en ``mode='before'``. Si llega contenido real, delega en
        ``validators.validar_polilinea_logica`` que impone tamaño mínimo/máximo.

        Args:
            v: polilínea codificada o cadena vacía o ``None``.

        Returns:
            ``None`` si venía vacío/``None``; el valor validado en caso contrario.

        Raises:
            AppValidationError: ``ROUTE_INVALID`` o ``ROUTE_TOO_LARGE`` si la polilínea no respeta los límites de tamaño.
        """
        if v == "":
            return None
        return validators.validar_polilinea_logica(v)

    @model_validator(mode="after")
    def validar_consistencia_temporal(self):
        """Comprobaciones cruzadas entre los distintos campos temporales y métricas.

        Se ejecuta en ``mode='after'`` para disponer de todos los valores
        ya parseados. Aplica, por orden:

        1. ``duracion_movimiento <= duracion_total``: no se puede moverse
           más tiempo del total registrado.
        2. ``duracion_parado <= duracion_total``: mismo principio.
        3. ``duracion_movimiento + duracion_parado == duracion_total``:
           la suma tiene que cuadrar; diferencias indican un bug del
           cliente en el desglose.
        4. ``duracion_pausa_manual <= duracion_total``: las pausas forman
           parte del total, no pueden superarlo.
        5. ``velocidad_max >= velocidad_media``: físicamente imposible que
           la máxima sea menor que la media.
        6. Si hay ``distancia > 0``, debe haber ``duracion_movimiento > 0``:
           no se hacen kilómetros en cero segundos.
        7. Si hay ``duracion_movimiento > 0``, debe venir
           ``ritmo_medio_movimiento > 0``: el cliente lo habría calculado.
        8. Si hay ``duracion_total > 0``, debe venir ``ritmo_medio_total > 0``.
        9. ``ritmo_maximo >= 0``: los ritmos son segundos por kilómetro,
           no pueden ser negativos.

        Estas comprobaciones protegen la base de datos de actividades con
        datos internamente contradictorios, que luego romperían agregados
        o rankings.

        Returns:
            La propia instancia si todas las comprobaciones pasan.

        Raises:
            AppValidationError: con códigos ``MOVING_DURATION_EXCEEDS_TOTAL``, ``STOPPED_DURATION_EXCEEDS_TOTAL``, ``DURATION_BREAKDOWN_MISMATCH``, ``MANUAL_PAUSE_EXCEEDS_TOTAL``, ``MAX_SPEED_BELOW_AVERAGE_SPEED``, ``MOVING_DURATION_REQUIRED_FOR_DISTANCE``, ``MOVING_PACE_REQUIRED``, ``TOTAL_PACE_REQUIRED`` o ``MAX_PACE_NEGATIVE`` según la regla que se haya violado.
        """
        # Valida consistencia temporal.
        if self.duracion_movimiento > self.duracion_total:
            raise AppValidationError(
                "Error: La duración en movimiento no puede superar la duración total",
                "MOVING_DURATION_EXCEEDS_TOTAL",
            )
        if self.duracion_parado > self.duracion_total:
            raise AppValidationError(
                "Error: La duración parada no puede superar la duración total",
                "STOPPED_DURATION_EXCEEDS_TOTAL",
            )
        if self.duracion_movimiento + self.duracion_parado != self.duracion_total:
            raise AppValidationError(
                "Error: La suma de duración en movimiento y parada debe coincidir con la duración total",
                "DURATION_BREAKDOWN_MISMATCH",
            )
        if self.duracion_pausa_manual > self.duracion_total:
            raise AppValidationError(
                "Error: La pausa manual no puede superar la duración total",
                "MANUAL_PAUSE_EXCEEDS_TOTAL",
            )
        if self.velocidad_max_x100 < self.velocidad_media_x100:
            raise AppValidationError(
                "Error: La velocidad máxima no puede ser menor que la velocidad media",
                "MAX_SPEED_BELOW_AVERAGE_SPEED",
            )
        if self.distancia > 0 and self.duracion_movimiento <= 0:
            raise AppValidationError(
                "Error: Una actividad con distancia debe tener tiempo en movimiento",
                "MOVING_DURATION_REQUIRED_FOR_DISTANCE",
            )
        if self.duracion_movimiento > 0 and self.ritmo_medio_movimiento <= 0:
            raise AppValidationError(
                "Error: Falta el ritmo medio en movimiento",
                "MOVING_PACE_REQUIRED",
            )
        if self.duracion_total > 0 and self.ritmo_medio_total <= 0:
            raise AppValidationError(
                "Error: Falta el ritmo medio total",
                "TOTAL_PACE_REQUIRED",
            )
        if self.ritmo_maximo < 0:
            raise AppValidationError(
                "Error: El ritmo máximo no puede ser negativo",
                "MAX_PACE_NEGATIVE",
            )
        return self


class EventoDiagnosticoActividad(BaseModel):
    """
    Evento individual de la línea temporal de diagnóstico.

    Cada evento representa un cambio relevante del seguimiento: creación del servicio,
    auto-pausa, reanudación, guardado, destrucción, etc.
    """

    at: datetime
    tipo: str = Field(..., min_length=1, max_length=64)
    detalle: Optional[str] = Field(default=None, max_length=500)

    @field_validator("tipo")
    @classmethod
    def validar_tipo(cls, valor: str) -> str:
        """Recorta el tipo de evento y rechaza cadenas vacías tras el recorte.

        El ``tipo`` actúa como categoría libre (``service_created``,
        ``auto_pause``, ``resume``...); no se valida contra una lista
        cerrada porque los builds internos pueden introducir eventos
        nuevos sin desplegar backend. La longitud máxima ya está en el
        ``Field`` de la clase.

        Args:
            valor: nombre del tipo de evento.

        Returns:
            El tipo recortado.

        Raises:
            AppValidationError: ``DIAGNOSTIC_EVENT_TYPE_REQUIRED`` si queda vacío tras recortar.
        """
        valor = valor.strip()
        if not valor:
            raise AppValidationError(
                "Error: El tipo de evento es obligatorio",
                "DIAGNOSTIC_EVENT_TYPE_REQUIRED",
            )
        return valor

    @field_validator("detalle")
    @classmethod
    def validar_detalle(cls, valor: Optional[str]) -> Optional[str]:
        """Recorta el detalle opcional y colapsa cadenas vacías a ``None``.

        Guardar cadenas vacías no aporta nada; colapsar a ``None``
        simplifica los filtros posteriores sobre la tabla de diagnóstico.

        Args:
            valor: texto libre con el detalle del evento, o ``None``.

        Returns:
            El detalle recortado si aporta contenido, o ``None`` si estaba vacío o solo con espacios.
        """
        if valor is None:
            return None
        valor = valor.strip()
        return valor or None


class GuardarActividadDiagnostico(BaseModel):
    """
    Carga útil del endpoint de diagnóstico de actividad.

    Se utiliza solo para builds internas con telemetría automática activada.
    No sustituye al carga útil de ``GuardarActividad`` y no afecta al cálculo de
    puntos, métricas agregadas ni ranking.
    """

    actividad_id: Optional[StrictInt] = Field(default=None)
    actividad_local_id: Optional[str] = Field(default=None, max_length=64)

    session_started_at: Optional[datetime] = None
    session_finished_at: Optional[datetime] = None
    last_timer_tick_at: Optional[datetime] = None
    service_created_at: Optional[datetime] = None
    service_destroyed_at: Optional[datetime] = None

    elapsed_seconds: StrictInt = Field(default=0)
    moving_seconds: StrictInt = Field(default=0)
    stopped_seconds: StrictInt = Field(default=0)
    manual_pause_seconds: StrictInt = Field(default=0)

    distance_meters: StrictInt = Field(default=0)
    average_pace_total: StrictInt = Field(default=0)
    average_pace_moving: StrictInt = Field(default=0)
    max_pace: StrictInt = Field(default=0)

    auto_pauses: StrictInt = Field(default=0)
    manual_pauses: StrictInt = Field(default=0)
    speed_alerts: StrictInt = Field(default=0)

    running_classified_seconds: StrictInt = Field(default=0)
    walking_classified_seconds: StrictInt = Field(default=0)
    service_restart_count: StrictInt = Field(default=0)

    current_status: Optional[str] = Field(default=None, max_length=40)
    app_version: Optional[str] = Field(default=None, max_length=64)
    os_version: Optional[str] = Field(default=None, max_length=64)
    manufacturer: Optional[str] = Field(default=None, max_length=64)
    model: Optional[str] = Field(default=None, max_length=128)

    # Bloques auxiliares serializados por backend como JSON textual.
    device_info: Optional[dict[str, Any]] = None
    event_log: List[EventoDiagnosticoActividad] = Field(default_factory=list)

    @field_validator(
        "actividad_local_id",
        "current_status",
        "app_version",
        "os_version",
        "manufacturer",
        "model",
    )
    @classmethod
    def limpiar_textos_opcionales(cls, valor: Optional[str]) -> Optional[str]:
        """Recorta los campos de texto descriptivos y colapsa vacíos a ``None``.

        Aplica a ``actividad_local_id``, ``current_status``, ``app_version``,
        ``os_version``, ``manufacturer`` y ``model``. Son campos puramente
        descriptivos; tener ``""`` vs ``None`` no es útil y ensuciaría los
        filtros en analítica.

        Args:
            valor: cadena opcional del campo.

        Returns:
            Cadena recortada si aporta contenido, o ``None`` si estaba vacía o solo con espacios.
        """
        if valor is None:
            return None
        valor = valor.strip()
        return valor or None

    @field_validator(
        "elapsed_seconds",
        "moving_seconds",
        "stopped_seconds",
        "manual_pause_seconds",
        "distance_meters",
        "average_pace_total",
        "average_pace_moving",
        "max_pace",
        "auto_pauses",
        "manual_pauses",
        "speed_alerts",
        "running_classified_seconds",
        "walking_classified_seconds",
        "service_restart_count",
    )
    @classmethod
    def validar_no_negativos(cls, valor: int) -> int:
        """Rechaza valores negativos en los contadores y duraciones del diagnóstico.

        Se aplica a todos los contadores numéricos enteros del diagnóstico
        (``elapsed_seconds``, ``moving_seconds``, ``distance_meters``, pausas,
        contadores de restart, etc.). Sus topes máximos no se fijan aquí
        porque el diagnóstico puede durar lo que dure una sesión de
        tracking extrema; el validator a nivel de modelo sí refuerza la
        consistencia entre campos.

        Args:
            valor: valor entero del campo.

        Returns:
            El mismo valor si es no negativo.

        Raises:
            AppValidationError: ``DIAGNOSTIC_NEGATIVE_VALUE`` si es negativo.
        """
        if valor < 0:
            raise AppValidationError(
                "Error: Los valores del diagnóstico no pueden ser negativos",
                "DIAGNOSTIC_NEGATIVE_VALUE",
            )
        return valor

    @model_validator(mode="after")
    def validar_consistencia(self):
        # Validación mínima para no persistir un breakdown temporal imposible.
        """Comprueba mínima consistencia temporal en el diagnóstico.

        Solo refuerza que ``moving_seconds`` y ``stopped_seconds`` no
        superen el total (``elapsed_seconds``). No exige que sumen
        exactamente porque el diagnóstico es informativo y puede haber
        pequeños desajustes entre timers que no invalidan el resto de
        campos; lo que sí sería un bug claro es que uno de los dos
        supere el total.

        Returns:
            La propia instancia si el desglose temporal es consistente.

        Raises:
            AppValidationError: ``DIAGNOSTIC_MOVING_EXCEEDS_ELAPSED`` si ``moving_seconds > elapsed_seconds``.
            AppValidationError: ``DIAGNOSTIC_STOPPED_EXCEEDS_ELAPSED`` si ``stopped_seconds > elapsed_seconds``.
        """
        if self.moving_seconds > self.elapsed_seconds:
            raise AppValidationError(
                "Error: El tiempo en movimiento no puede superar el tiempo total",
                "DIAGNOSTIC_MOVING_EXCEEDS_ELAPSED",
            )
        if self.stopped_seconds > self.elapsed_seconds:
            raise AppValidationError(
                "Error: El tiempo parado no puede superar el tiempo total",
                "DIAGNOSTIC_STOPPED_EXCEEDS_ELAPSED",
            )
        return self


class RespuestaGuardarActividadDiagnostico(BaseModel):
    """Respuesta simple del endpoint de diagnóstico de actividad."""

    estatus: str
    mensaje: str
    diagnostico_id: int


class RespuestaObtenerActividad(BaseModel):
    """Representa respuesta obtener actividad."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    tipo: str
    distancia: StrictInt = Field(...)
    duracion_total: int
    duracion_movimiento: int
    duracion_parado: int
    duracion_pausa_manual: int
    calorias_quemadas: int
    pasos: Optional[int] = None
    ritmo_medio_movimiento: int
    ritmo_medio_total: int
    ritmo_maximo: int
    velocidad_media_x100: int
    velocidad_max_x100: int
    auto_pausas: int
    pausas_manuales: int
    alertas_velocidad: int
    ruta_polilinea: Optional[str] = Field(None, max_length=200000)
    ruta_mapa_url: Optional[str] = None
    fecha_ruta: datetime
    nuevo_total_puntos: Optional[int] = None


class RespuestaObtenerActividadesPaginada(BaseModel):
    """Representa respuesta obtener actividades paginada."""

    items: List[RespuestaObtenerActividad]
    total: int
    skip: int
    limit: int
    has_more: bool


class RespuestaBorrarActividad(BaseModel):
    """Representa respuesta borrar actividad."""

    estatus: str
    mensaje: str
    nuevo_total_puntos: int


class ObtenerRanking(BaseModel):
    """Representa obtener ranking."""

    posicion: int
    nombre_usuario: str
    foto_perfil: Optional[str] = None
    foto_version: int = 0
    total_puntos: int
    total_metros: int


class RespuestaGenerica(BaseModel):
    """Representa respuesta generica."""

    estatus: str
    mensaje: str
