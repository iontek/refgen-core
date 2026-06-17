from svc_base.audit import AuditEvent, record_audit
from svc_base.db import Base, make_engine, make_session_factory


def test_record_audit(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path}/audit.db")
    Base.metadata.create_all(eng)
    db = make_session_factory(eng)()
    try:
        record_audit(db, action="panel.lock", actor="u1", tenant_id="tuseb",
                     entity_type="panel", entity_id="panel-1",
                     detail={"bump": "minor"})
        db.commit()
        rows = db.query(AuditEvent).all()
        assert len(rows) == 1
        assert rows[0].action == "panel.lock"
        assert rows[0].tenant_id == "tuseb"
        assert rows[0].entity_id == "panel-1"
        assert rows[0].detail == {"bump": "minor"}
    finally:
        db.close()
