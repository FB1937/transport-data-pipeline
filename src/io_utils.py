from pathlib import Path

import pandas as pd


def read_csv_with_fallback(path: Path) -> pd.DataFrame:
    errors: list[str] = []
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError as error:
            errors.append(f"{encoding}: {error}")
    raise UnicodeError("CSV 인코딩을 확인할 수 없습니다. " + " / ".join(errors))
