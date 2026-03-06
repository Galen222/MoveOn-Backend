# tests/test_identity_rate_limit.py

import pytest

from services.identity_rate_limit import (
    _BUCKETS,
    IdentityRateLimitExceeded,
    check_identity_limit,
)


def setup_function():
    _BUCKETS.clear()


def test_registro_identity_rate_limit():
    for _ in range(5):
        check_identity_limit("registro", "correo@test.com", "5/hour")

    with pytest.raises(IdentityRateLimitExceeded):
        check_identity_limit("registro", "correo@test.com", "5/hour")