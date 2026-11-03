from pathlib import Path
import sqlite3

from src.collect_data import _download, _download_odcloud, collect


def test_download_writes_atomically(tmp_path, monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, size):
            if hasattr(self, "done"):
                return b""
            self.done = True
            return b"header\nvalue\n"

    monkeypatch.setattr("src.collect_data.urlopen", lambda request, timeout: Response())
    destination = tmp_path / "source.csv"
    metadata = _download("https://example.test/source.csv", destination)
    assert destination.read_bytes() == b"header\nvalue\n"
    assert metadata["bytes"] == 13
    assert not Path(str(destination) + ".part").exists()


def test_download_odcloud_paginates_json(tmp_path, monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, size=-1):
            import json

            return json.dumps(self.payload).encode()

    responses = iter(
        [
            {"totalCount": 2, "data": [{"운행일자": "2025-01-01", "이용량": 1}]},
            {"totalCount": 2, "data": [{"운행일자": "2025-01-02", "이용량": 2}]},
        ]
    )
    monkeypatch.setattr("src.collect_data.OD_CLOUD_API_KEY", "test-key")
    monkeypatch.setattr("src.collect_data.urlopen", lambda request, timeout: Response(next(responses)))
    destination = tmp_path / "hourly.csv"
    metadata = _download_odcloud("https://api.odcloud.kr/api/test", destination)
    assert "운행일자,이용량" in destination.read_text(encoding="utf-8-sig")
    assert metadata["rows"] == 2
    assert not Path(str(destination) + ".part").exists()


def test_collect_records_failure_history(tmp_path, monkeypatch):
    source = tmp_path / "source.csv"
    monkeypatch.setattr("src.collect_data.RAW_SOURCES", {source: "https://example.test/source.csv"})
    monkeypatch.setattr("src.collect_data.RAW_DIR", tmp_path)
    monkeypatch.setattr("src.collect_data.SQLITE_FILE", tmp_path / "history.sqlite")
    monkeypatch.setattr("src.collect_data.COLLECTION_RETRIES", 1)
    monkeypatch.setattr(
        "src.collect_data._download",
        lambda url, destination: (_ for _ in ()).throw(ValueError("의도적 테스트 오류")),
    )

    assert collect() == 1
    with sqlite3.connect(tmp_path / "history.sqlite") as connection:
        row = connection.execute(
            "SELECT status, error FROM collection_runs ORDER BY run_id DESC LIMIT 1"
        ).fetchone()
    assert row == ("failed", "의도적 테스트 오류")
