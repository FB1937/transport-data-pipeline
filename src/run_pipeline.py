from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from .config import PROJECT_ROOT


LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "pipeline.log"
STEPS = ("src.inspect_data", "src.clean_data", "src.load_sqlite", "src.analyze", "src.dashboard")
MAX_ATTEMPTS = 2


def configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
    )


def main() -> int:
    configure_logging()
    for step in STEPS:
        logging.info("START %s", step)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            completed = subprocess.run(
                [sys.executable, "-m", step],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            if completed.returncode == 0:
                break
            logging.error("FAILED %s attempt=%s/%s", step, attempt, MAX_ATTEMPTS)
            if attempt < MAX_ATTEMPTS:
                logging.info("RETRY %s", step)
        if completed.stdout:
            logging.info("%s", completed.stdout.rstrip())
        if completed.stderr:
            logging.warning("%s", completed.stderr.rstrip())
        if completed.returncode != 0:
            logging.error("FAILED %s (exit=%s) after %s attempts", step, completed.returncode, MAX_ATTEMPTS)
            return completed.returncode
        logging.info("DONE %s", step)
    logging.info("PIPELINE COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
