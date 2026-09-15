from slowapi import Limiter
from slowapi.util import get_remote_address

from .settings import get_settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[get_settings().rate_limit_default],
)
