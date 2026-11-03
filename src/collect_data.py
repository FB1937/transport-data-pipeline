from __future__ import annotations

import hashlib
import json
import logging
import sys
import time
import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .config import (
    COLLECTION_RETRIES,
    COLLECTION_TIMEOUT_SECONDS,
    OD_CLOUD_API_KEY,
    OD_CLOUD_PER_PAGE,
    RAW_DIR,
    RAW_SOURCES,
    SQLITE_FILE,
)


LOG = logging.getLogger(__name__)
USER_AGENT = "transit-data-pipeline/1.0"


def _record_collection_run(status: str, metadata: dict[str, object], error: str = "") -> None:
    SQLITE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(SQLITE_FILE) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS collection_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                status TEXT NOT NULL,
                details_json TEXT NOT NULL,
                error TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO collection_runs
                (started_at, completed_at, status, details_json, error)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                metadata.get("_started_at", datetime.now(timezone.utc).isoformat()),
                datetime.now(timezone.utc).isoformat(),
                status,
                json.dumps({key: value for key, value in metadata.items() if key != "_started_at"}, ensure_ascii=False),
                error,
            ),
        )


def _is_odcloud_api(url: str) -> bool:
    return urlsplit(url).netloc == "api.odcloud.kr"


def _api_url(url: str, page: int) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(
        {
            "page": str(page),
            "perPage": str(OD_CLOUD_PER_PAGE),
            "returnType": "JSON",
            "serviceKey": OD_CLOUD_API_KEY,
        }
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _download_odcloud(url: str, destination: Path) -> dict[str, object]:
    if not OD_CLOUD_API_KEY:
        raise ValueError("OD_CLOUD_API_KEY 환경변수가 필요합니다.")

    rows: list[dict[str, object]] = []
    page = 1
    total_count: int | None = None
    while total_count is None or len(rows) < total_count:
        request = Request(
            _api_url(url, page),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        with urlopen(request, timeout=COLLECTION_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("공공데이터 API 응답에 data 배열이 없습니다.")
        page_rows = payload["data"]
        rows.extend(row for row in page_rows if isinstance(row, dict))
        total_count = int(payload.get("totalCount", len(rows)))
        if not page_rows:
            break
        page += 1

    if not rows:
        raise ValueError(f"공공데이터 API가 빈 응답을 반환했습니다: {url}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    fieldnames = list(rows[0])
    try:
        with temporary.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        content = temporary.read_bytes()
        temporary.replace(destination)
        return {
            "url": url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "rows": len(rows),
        }
    finally:
        temporary.unlink(missing_ok=True)


def _download(url: str, destination: Path) -> dict[str, object]:
    if _is_odcloud_api(url):
        return _download_odcloud(url, destination)
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
    started_at = datetime.now(timezone.utc).isoformat()
    configured = [(path, url) for path, url in RAW_SOURCES.items() if url]
    missing = [path for path, url in RAW_SOURCES.items() if not path.exists()]
    if not configured:
        if missing:
            LOG.error("수집 URL이 없고 원본 파일도 없습니다: %s", missing)
            _record_collection_run("failed", {"_started_at": started_at}, "원본 파일이 없습니다.")
            return 1
        LOG.info("수집 URL이 설정되지 않아 기존 원본을 유지합니다.")
        _record_collection_run("skipped", {"_started_at": started_at}, "")
        return 0

    metadata: dict[str, object] = {"_started_at": started_at}
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
                    _record_collection_run("failed", metadata, str(error))
                    return 1
                time.sleep(min(2 ** (attempt - 1), 8))

    remaining = [path for path in RAW_SOURCES if not path.exists()]
    if remaining:
        LOG.error("수집 후에도 원본 파일이 없습니다: %s", remaining)
        _record_collection_run("failed", metadata, f"수집 후 원본 파일이 없습니다: {remaining}")
        return 1
    (RAW_DIR / "collection_manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _record_collection_run("success", metadata)
    LOG.info("수집 완료: %s개 파일", len(metadata) - 1)
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return collect()


if __name__ == "__main__":
    sys.exit(main())
