import re
from io import StringIO

import pandas as pd
import requests

from common.csv_utils import save_csv


SOURCES = {
    "S高": "https://kabutan.jp/warning/?mode=3_1",
    "S安": "https://kabutan.jp/warning/?mode=3_2",
}

COLUMNS = ["コード", "銘柄名", "前日比"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

EXCLUDE_CODES = {"0000", "0800", "0823", "0950"}
VALID_MARKETS = {"東Ｐ", "東Ｓ", "東Ｇ"}


def fetch_html(url: str) -> str:
    res = requests.get(url, headers=HEADERS, timeout=25)
    res.raise_for_status()
    res.encoding = res.apparent_encoding
    return res.text


def clean_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).replace("\n", " ").replace("\r", " ").strip()


def is_stock_code(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9]{3}[0-9A-Z]", str(value).strip()))


def normalize_market(value: str) -> str:
    value = clean_text(value)

    if "東証Ｐ" in value or "プライム" in value:
        return "東Ｐ"
    if "東証Ｓ" in value or "スタンダード" in value:
        return "東Ｓ"
    if "東証Ｇ" in value or "グロース" in value:
        return "東Ｇ"
    if value in VALID_MARKETS:
        return value

    return ""


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            "_".join([str(x) for x in col if str(x) != "nan"]).strip()
            for col in df.columns
        ]
    else:
        df.columns = [str(c).strip() for c in df.columns]
    return df


def find_day_change(row: pd.Series, df: pd.DataFrame) -> str:
    for col in df.columns:
        col_name = str(col)
        if "前日比" in col_name or "騰落率" in col_name:
            value = clean_text(row[col])
            if value:
                return value

    cells = [clean_text(x) for x in row.tolist()]
    for cell in cells:
        if "%" in cell and re.search(r"[+-]?\d", cell):
            return cell

    return ""


def extract_rows(url: str) -> list[dict]:
    html = fetch_html(url)

    try:
        tables = pd.read_html(StringIO(html))
    except ValueError:
        return []

    results = []

    for table in tables:
        df = flatten_columns(table.copy())

        for _, row in df.iterrows():
            cells = [clean_text(x) for x in row.tolist()]
            cells = [x for x in cells if x]

            code = ""
            code_index = None

            for i, cell in enumerate(cells):
                if is_stock_code(cell):
                    code = cell
                    code_index = i
                    break

            if not code or code in EXCLUDE_CODES:
                continue

            market = ""
            for cell in cells:
                m = normalize_market(cell)
                if m in VALID_MARKETS:
                    market = m
                    break

            if market not in VALID_MARKETS:
                continue

            name = ""

            for col in df.columns:
                if "銘柄" in str(col):
                    candidate = clean_text(row[col])
                    if candidate and candidate != code and not is_stock_code(candidate):
                        name = candidate
                        break

            if not name and code_index is not None:
                for candidate in cells[code_index + 1:]:
                    if (
                        candidate
                        and candidate != code
                        and normalize_market(candidate) not in VALID_MARKETS
                        and not is_stock_code(candidate)
                        and not re.fullmatch(r"[-+0-9.,%]+", candidate)
                    ):
                        name = candidate
                        break

            if not name:
                continue

            day_change = find_day_change(row, df)

            results.append({
                "コード": code,
                "銘柄名": name,
                "前日比": day_change,
            })

    return results


def collect() -> list[dict]:
    rows = []

    for label, url in SOURCES.items():
        print(f"取得中: {label} - {url}")

        try:
            data = extract_rows(url)
            print(f"  -> {len(data)}件取得")
            rows.extend(data)

        except Exception as e:
            print(f"  -> 取得失敗: {label} / {e}")

    if not rows:
        return []

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["コード"])

    return df[COLUMNS].to_dict("records")


def main():
    return save_csv(
        collect(),
        "stop_high_low.csv",
        COLUMNS,
    )


if __name__ == "__main__":
    main()