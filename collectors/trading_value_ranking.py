import re
import time
from io import StringIO

import pandas as pd
import requests

from common.csv_utils import save_csv


BASE_URL = "https://kabutan.jp"
START_URL = "https://kabutan.jp/warning/trading_value_ranking"

COLUMNS = ["コード", "銘柄名", "市場", "売買代金", "前日比"]

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


def find_value_by_column(row, df: pd.DataFrame, keywords: list[str]) -> str:
    for col in df.columns:
        col_name = str(col)
        if any(keyword in col_name for keyword in keywords):
            value = clean_text(row[col])
            if value:
                return value
    return ""


def extract_rows_from_url(url: str) -> list[dict]:
    html = fetch_html(url)

    try:
        tables = pd.read_html(StringIO(html))
    except ValueError:
        return []

    rows = []

    for table in tables:
        df = flatten_columns(table.copy())

        for _, row in df.iterrows():
            cells = [clean_text(x) for x in row.tolist()]
            cells = [x for x in cells if x]

            if not cells:
                continue

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

            trading_value = find_value_by_column(row, df, ["売買代金"])
            day_change = find_value_by_column(row, df, ["前日比"])

            rows.append({
                "コード": code,
                "銘柄名": name,
                "市場": market,
                "売買代金": trading_value,
                "前日比": day_change,
            })

    return rows


def collect() -> list[dict]:
    all_rows = []

    for page in range(1, 10):
        url = START_URL if page == 1 else f"{START_URL}?page={page}"
        print(f"取得中: {url}")

        try:
            rows = extract_rows_from_url(url)
            print(f"  -> {len(rows)}件取得")
            all_rows.extend(rows)
        except Exception as e:
            print(f"  -> 取得失敗: {e}")

        if all_rows:
            temp_df = pd.DataFrame(all_rows).drop_duplicates(subset=["コード"])
            if len(temp_df) >= 50:
                break

        time.sleep(1)

    if not all_rows:
        return []

    df = pd.DataFrame(all_rows)
    df = df.drop_duplicates(subset=["コード"]).head(50)

    return df[COLUMNS].to_dict("records")


def main():
    return save_csv(
        collect(),
        "trading_value_ranking.csv",
        COLUMNS,
    )


if __name__ == "__main__":
    main()