import pytest
from fastapi import HTTPException

from svc_base.versioning import assert_mutable, bump_semver, content_hash


def test_content_hash_deterministic_and_order_independent():
    a = content_hash({"x": 1, "y": [1, 2, 3]})
    b = content_hash({"y": [1, 2, 3], "x": 1})
    assert a == b                       # key order irrelevant
    assert len(a) == 64                 # sha256 hex
    assert a != content_hash({"x": 2, "y": [1, 2, 3]})


def test_bump_semver():
    assert bump_semver("1.2.3", "major") == "2.0.0"
    assert bump_semver("1.2.3", "minor") == "1.3.0"
    assert bump_semver("1.2.3", "patch") == "1.2.4"
    assert bump_semver("0.0.0") == "0.1.0"


def test_assert_mutable():
    assert_mutable("draft")             # no raise
    for st in ("locked", "archived"):
        with pytest.raises(HTTPException) as e:
            assert_mutable(st)
        assert e.value.status_code == 409
