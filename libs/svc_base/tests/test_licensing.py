import pytest
from fastapi import HTTPException

from svc_base.auth import Principal, _decode, issue_token
from svc_base.config import BaseServiceSettings
from svc_base.licensing import has_entitlement, require_entitlement


def _p(ents):
    return Principal("u1", ["designer"], {"tenant_id": "t", "entitlements": ents})


def test_has_entitlement():
    p = _p(["design", "analysis"])
    assert has_entitlement(p, "design")
    assert not has_entitlement(p, "run-control")


def test_require_entitlement_allows():
    p = _p(["analysis"])
    assert require_entitlement("analysis")(p) is p


def test_require_entitlement_denies():
    p = _p(["design"])
    with pytest.raises(HTTPException) as e:
        require_entitlement("analysis")(p)
    assert e.value.status_code == 403


def test_token_carries_entitlements():
    s = BaseServiceSettings(jwt_secret="x")
    tok = issue_token(s, "u1", tenant_id="t", entitlements=["design"])
    assert _decode(tok, s)["entitlements"] == ["design"]
