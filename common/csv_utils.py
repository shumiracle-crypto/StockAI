from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
MARKETDATA_DIR = BASE_DIR / "marketdata"
MARKETDATA_DIR.mkdir(exist_ok=True)


def save_csv(rows: list[dict], filename: str, columns: list[str]) -> Path:
    path = MARKETDATA_DIR / filename

    if rows:
        df = pd.DataFrame(rows)
        df = df.reindex(columns=columns)
    else:
        df = pd.DataFrame(columns=columns)

    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path