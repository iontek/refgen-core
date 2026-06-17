from sqlalchemy import Column, Integer
from sqlalchemy.orm import declarative_base

from svc_base.auth import Principal, _decode, issue_token
from svc_base.config import BaseServiceSettings
from svc_base.tenancy import TenantScopedMixin, tenant_subtree


def test_tenant_subtree():
    # Refgen → TÜSEB → {distA, distB}; distA → hosp1
    parents = {"tuseb": "refgen", "distA": "tuseb", "distB": "tuseb", "hosp1": "distA"}
    assert tenant_subtree("refgen", parents) == {
        "refgen", "tuseb", "distA", "distB", "hosp1"
    }
    assert tenant_subtree("tuseb", parents) == {"tuseb", "distA", "distB", "hosp1"}
    assert tenant_subtree("distA", parents) == {"distA", "hosp1"}
    assert tenant_subtree("hosp1", parents) == {"hosp1"}


def test_mixin_adds_tenant_column():
    Base = declarative_base()

    class Thing(TenantScopedMixin, Base):
        __tablename__ = "thing"
        id = Column(Integer, primary_key=True)

    assert "tenant_id" in Thing.__table__.columns


def test_principal_reads_tenant():
    p = Principal("u1", ["admin"], {"tenant_id": "tuseb", "user_id": "u1"})
    assert p.tenant_id == "tuseb"


def test_token_carries_tenant():
    s = BaseServiceSettings(jwt_secret="secret", jwt_algorithm="HS256")
    tok = issue_token(s, subject="u1", roles=["designer"], tenant_id="tuseb")
    claims = _decode(tok, s)
    assert claims["tenant_id"] == "tuseb"
    assert claims["user_id"] == "u1"
    assert claims["roles"] == ["designer"]
