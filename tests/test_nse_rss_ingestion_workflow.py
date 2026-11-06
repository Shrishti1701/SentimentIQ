from pathlib import Path

import ingestion.nse_rss_test as workflow
from ingestion.nse_rss_persistence import IngestionReport


FIXTURE = Path(__file__).parent / "fixtures" / "nse_rss_synthetic.xml"


def test_manual_workflow_persists_without_analysis(monkeypatch, capsys):
    class Response:
        status_code = 200
        ok = True
        content = FIXTURE.read_bytes()
        text = content.decode("utf-8")
        encoding = "utf-8"
        headers = {"Content-Type": "application/rss+xml"}

    monkeypatch.setattr(workflow.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(workflow, "settings", type("Settings", (), {"database_url": "sqlite:///:memory:"})())
    monkeypatch.setattr(workflow, "create_engine", lambda *args, **kwargs: object())
    monkeypatch.setattr(workflow, "sessionmaker", lambda **kwargs: object())

    captured = {}

    def persist(records, factory):
        captured["record_count"] = len(records)
        captured["factory"] = factory
        return IngestionReport(inserted_count=2, duplicate_count=0)

    monkeypatch.setattr(workflow, "persist_announcements", persist)

    assert workflow.fetch_and_display() == 0
    output = capsys.readouterr().out
    assert captured["record_count"] == 2
    assert captured["factory"] is not None
    assert "Records inserted: 2" in output
