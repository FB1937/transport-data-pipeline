from pathlib import Path

from src.collect_data import _download, _download_odcloud


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
