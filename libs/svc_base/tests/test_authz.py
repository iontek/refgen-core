import pytest
from fastapi import HTTPException

from svc_base.auth import Principal, _decode, assert_tenant_access, issue_token
from svc_base.config import BaseServiceSettings


def _p(tenant=None, scope=None):
    claims = {}
    if tenant:
        claims["tenant_id"] = tenant
    if scope is not None:
        claims["scope"] = scope
    return Principal("u1", ["designer"], claims)


def test_scope_defaults_to_own_tenant():
    assert _p(tenant="tuseb").scope == ["tuseb"]


def test_same_tenant_allowed():
    assert_tenant_access(_p(tenant="tuseb"), "tuseb")  # no raise


def test_cross_tenant_denied():
    with pytest.raises(HTTPException) as e:
        assert_tenant_access(_p(tenant="tuseb"), "genera")
    assert e.value.status_code == 403


def test_subtree_scope_allows_descendant():
    p = _p(tenant="tuseb", scope=["tuseb", "distA", "hosp1"])
    assert_tenant_access(p, "hosp1")  # operator reaches its subtree


def test_token_carries_scope():
    s = BaseServiceSettings(jwt_secret="x")
    tok = issue_token(s, "u1", tenant_id="tuseb", scope=["tuseb", "distA"])
    assert _decode(tok, s)["scope"] == ["tuseb", "distA"]
