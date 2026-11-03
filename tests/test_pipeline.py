from pathlib import Path

from src.config import PROJECT_ROOT
from src.run_pipeline import LOG_FILE, STEPS


def test_pipeline_has_expected_steps():
    assert STEPS == (
        "src.collect_data",
        "src.inspect_data",
        "src.clean_data",
        "src.load_sqlite",
        "src.analyze",
        "src.dashboard",
    )
    assert LOG_FILE == PROJECT_ROOT / Path("logs/pipeline.log")
