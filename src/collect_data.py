from __future__ import annotations

import hashlib
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import COLLECTION_RETRIES, COLLECTION_TIMEOUT_SECONDS, RAW_DIR, RAW_SOURCES


LOG = logging.getLogger(__name__)
USER_AGENT = "transit-data-pipeline/1.0"


def _download(url: str, destination: Path) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv,application/octet-stream"})
    try:
        with urlopen(request, timeout=COLLECTION_TIMEOUT_SECONDS) as response, temporary.open("wb") as output:
            digest = hashlib.sha256()
            size = 0
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        if size == 0:
            raise ValueError(f"빈 응답입니다: {url}")
        temporary.replace(destination)
        return {
            "url": url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "bytes": size,
            "sha256": digest.hexdigest(),
        }
    finally:
        temporary.unlink(missing_ok=True)


def collect() -> int:
    configured = [(path, url) for path, url in RAW_SOURCES.items() if url]
    missing = [path for path, url in RAW_SOURCES.items() if not path.exists()]
    if not configured:
        if missing:
            LOG.error("수집 URL이 없고 원본 파일도 없습니다: %s", missing)
            return 1
        LOG.info("수집 URL이 설정되지 않아 기존 원본을 유지합니다.")
        return 0

    metadata: dict[str, object] = {}
    for destination, url in configured:
        for attempt in range(1, COLLECTION_RETRIES + 1):
            try:
                LOG.info("DOWNLOAD %s attempt=%s/%s", destination.name, attempt, COLLECTION_RETRIES)
                metadata[destination.name] = _download(url, destination)
                break
            except (HTTPError, URLError, OSError, TimeoutError, ValueError) as error:
                LOG.warning("DOWNLOAD FAILED %s: %s", destination.name, error)
                if attempt == COLLECTION_RETRIES:
                    LOG.error("수집 실패 후 기존 파일을 보존합니다: %s", destination)
                    return 1
                time.sleep(min(2 ** (attempt - 1), 8))

    remaining = [path for path in RAW_SOURCES if not path.exists()]
    if remaining:
        LOG.error("수집 후에도 원본 파일이 없습니다: %s", remaining)
        return 1
    (RAW_DIR / "collection_manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    LOG.info("수집 완료: %s개 파일", len(metadata))
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return collect()


if __name__ == "__main__":
    sys.exit(main())
