import json

import pytest
from fastapi import HTTPException

from svc_base.versioning import (
    assert_lockable,
    assert_mutable,
    assert_validatable,
    bump_semver,
    content_hash,
    reference_versions,
)


def test_content_hash_deterministic_and_order_independent():
    a = content_hash({"x": 1, "y": [1, 2, 3]})
    b = content_hash({"y": [1, 2, 3], "x": 1})
    assert a == b                       # key order irrelevant
    assert a.startswith("sha256:")      # platform-compatible format
    assert len(a) == len("sha256:") + 64  # prefix + sha256 hex
    assert a != content_hash({"x": 2, "y": [1, 2, 3]})


def test_bump_semver():
    assert bump_semver("1.2.3", "major") == "2.0.0"
    assert bump_semver("1.2.3", "minor") == "1.3.0"
    assert bump_semver("1.2.3", "patch") == "1.2.4"
    assert bump_semver("0.0.0") == "0.1.0"


def test_bump_semver_first_lock_is_1_0_0():
    # No prior version → first lock is 1.0.0 regardless of bump level (parity
    # with platform state.bump_semver).
    assert bump_semver(None) == "1.0.0"
    assert bump_semver("") == "1.0.0"
    assert bump_semver(None, "patch") == "1.0.0"
    assert bump_semver("garbage") == "1.0.0"


def test_assert_mutable():
    assert_mutable("draft")             # no raise
    for st in ("locked", "archived"):
        with pytest.raises(HTTPException) as e:
            assert_mutable(st)
        assert e.value.status_code == 409


def test_reference_versions_defaults(monkeypatch):
    monkeypatch.delenv("REF_VERSIONS_JSON", raising=False)
    monkeypatch.delenv("REF_VERSIONS_PATH", raising=False)
    rv = reference_versions()
    assert rv["genome_build"] == "GRCh38"
    assert rv["mane_release"] == "1.5"


def test_reference_versions_env_override(monkeypatch):
    monkeypatch.setenv("REF_VERSIONS_JSON",
                       json.dumps({"genome_build": "GRCh37", "mane_release": "1.3"}))
    rv = reference_versions()
    assert rv["genome_build"] == "GRCh37"
    assert rv["mane_release"] == "1.3"


def test_validity_guards():
    # happy path: no raise
    assert_validatable("draft", 1)
    assert_lockable("validated", 3)

    # wrong state OR no genes → 422 with the reasons
    for fn, status in ((assert_validatable, "locked"), (assert_lockable, "draft")):
        with pytest.raises(HTTPException) as e:
            fn(status, 0)
        assert e.value.status_code == 422
        assert "panel has no genes" in e.value.detail
