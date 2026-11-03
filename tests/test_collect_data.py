from pathlib import Path

from src.collect_data import _download


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
