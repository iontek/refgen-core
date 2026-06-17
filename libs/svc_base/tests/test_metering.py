from svc_base.db import Base, make_engine, make_session_factory
from svc_base.metering import UsageEvent, record_usage, unreported


def test_record_and_outbox(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path}/usage.db")
    Base.metadata.create_all(eng)
    db = make_session_factory(eng)()
    try:
        record_usage(db, tenant_id="tuseb", feature="analysis", quantity=1, actor="u1")
        record_usage(db, tenant_id="tuseb", feature="analysis", quantity=2, actor="u1")
        db.commit()

        pending = unreported(db)
        assert len(pending) == 2
        assert all(not e.reported for e in pending)

        pending[0].reported = True       # relay ships it
        db.commit()
        assert len(unreported(db)) == 1
    finally:
        db.close()
