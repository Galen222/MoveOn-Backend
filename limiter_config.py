# limiter_config.py

from slowapi import Limiter
from slowapi.util import get_remote_address

# Inicializar el limitador usando la dirección IP del usuario como "llave"
# para identificar quién está haciendo las peticiones.
limiter = Limiter(key_func=get_remote_address)