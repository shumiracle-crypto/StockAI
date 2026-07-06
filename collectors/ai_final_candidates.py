import re
import time
from io import StringIO

import pandas as pd
import requests
from bs4 import BeautifulSoup

from common.csv_utils import save_csv


KABUTAN_SOURCES = {
    "PTS": "https://kabutan.jp/warning/pts_night_price_increase",
    "出来高急増": "https://kabutan.jp/warning/volume_ranking",
    "値上がり率": "https://kabutan.jp/warning/?mode=2_1",
}

TDNET_SEARCH_URLS = [
    "https://tdnet-search.appspot.com/?mode=recent",
    "https://tdnet-search.appspot.com/",
]

COLUMNS = [
    "コード",
    "銘柄名",
    "市場",
    "理由数",
    "該当理由",
    "適時開示タイトル",
]

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

TDNET_EXCLUDE_KEYWORDS = [
    "訂正", "一部訂正", "役員", "人事", "異動", "定款",
    "コーポレート・ガバナンス", "コーポレートガバナンス",
    "独立役員", "支配株主", "議決権", "株主総会",
    "有価証券報告書", "内部統制", "確認書", "大量保有",
    "臨時報告書", "自己株式の取得状況", "取得状況",
    "月次", "売上速報", "資金の借入", "借入",
    "優待制度の廃止", "株主優待制度の廃止", "減配",
    "下方修正", "特別損失", "減損", "希望退職",
    "事業撤退", "上場廃止", "監理銘柄", "継続企業の前提",
]

TDNET_INCLUDE_KEYWORDS = [
    "上方修正", "業績予想の修正", "業績予想修正",
    "通期業績予想", "連結業績予想", "増配", "復配",
    "初配", "配当予想の修正", "配当予想修正",
    "自己株式取得", "自己株式の取得", "自社株買い",
    "株式分割", "公開買付", "ＴＯＢ", "TOB", "MBO",
    "資本業務提携", "業務提携", "資本提携", "提携",
    "大型受注", "受注", "契約締結", "販売開始",
    "提供開始", "新製品", "新サービス", "承認", "認可",
    "許可", "採択", "補助金", "助成金", "特許",
    "黒字転換", "営業黒字", "譲渡益", "固定資産の譲渡",
    "子会社化", "株主優待", "優待制度",
]

REASON_ORDER = ["PTS", "出来高急増", "値上がり率", "年初来高値", "適時開示"]


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


def should_keep_tdnet_title(title: str) -> bool:
    title = clean_text(title)

    if not title:
        return False

    if any(keyword in title for keyword in TDNET_EXCLUDE_KEYWORDS):
        return False

    return any(keyword in title for keyword in TDNET_INCLUDE_KEYWORDS)


def extract_kabutan(reason: str, url: str) -> list[dict]:
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

            if name:
                results.append({
                    "コード": code,
                    "銘柄名": name,
                    "市場": market,
                    "該当理由": reason,
                    "適時開示タイトル": "",
                })

    return results


def parse_tdnet_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    links = soup.find_all("a")

    rows = []
    i = 0

    while i < len(links) - 2:
        code_text = links[i].get_text(strip=True)

        if re.fullmatch(r"[0-9]{4}0", code_text) or re.fullmatch(r"[0-9]{3}[A-Z]0", code_text):
            code = code_text[:-1]
            name = links[i + 1].get_text(strip=True)
            title = clean_text(links[i + 2].get_text(strip=True))
            href = links[i + 2].get("href", "")

            if "release.tdnet.info" in href and title and should_keep_tdnet_title(title):
                rows.append({
                    "コード": code,
                    "銘柄名": name,
                    "市場": "",
                    "該当理由": "適時開示",
                    "適時開示タイトル": title,
                })

                i += 3
                continue

        i += 1

    return rows


def extract_tdnetsearch() -> list[dict]:
    all_rows = []

    for url in TDNET_SEARCH_URLS:
        print(f"取得中: TDnetSearch - {url}")

        try:
            html = fetch_html(url)
            rows = parse_tdnet_html(html)
            print(f"  -> TDnet抽出 {len(rows)}件")

            if rows:
                all_rows.extend(rows)
                break

        except Exception as e:
            print(f"  -> TDnetSearch取得失敗: {e}")

        time.sleep(1)

    deduped = []
    seen = set()

    for row in all_rows:
        key = (row["コード"], row["適時開示タイトル"])
        if key in seen:
            continue

        seen.add(key)
        deduped.append(row)

    return deduped


def collect() -> list[dict]:
    rows = []

    for reason, url in KABUTAN_SOURCES.items():
        print(f"取得中: {reason} - {url}")

        try:
            data = extract_kabutan(reason, url)
            print(f"  -> {len(data)}件取得")
            rows.extend(data)

        except Exception as e:
            print(f"  -> 取得失敗: {reason} / {e}")

        time.sleep(1)

    tdnet_rows = extract_tdnetsearch()
    rows.extend(tdnet_rows)

    if not rows:
        return []

    raw_df = pd.DataFrame(rows)

    code_to_name = {}
    code_to_market = {}

    for _, row in raw_df.iterrows():
        code = row["コード"]
        name = row["銘柄名"]
        market = row["市場"]

        if name and name != code:
            code_to_name[code] = name

        if market:
            code_to_market[code] = market

    raw_df["銘柄名"] = raw_df.apply(
        lambda r: code_to_name.get(r["コード"], r["銘柄名"]),
        axis=1,
    )

    raw_df["市場"] = raw_df.apply(
        lambda r: code_to_market.get(r["コード"], r["市場"]),
        axis=1,
    )

    merged = (
        raw_df.groupby("コード", as_index=False)
        .agg({
            "銘柄名": lambda x: next((v for v in x if v), ""),
            "市場": lambda x: next((v for v in x if v), ""),
            "該当理由": lambda x: "・".join([r for r in REASON_ORDER if r in set(x)]),
            "適時開示タイトル": lambda x: " / ".join([v for v in x if v]),
        })
    )

    merged["理由数"] = merged["該当理由"].apply(lambda x: len(x.split("・")) if x else 0)
    merged["PTSフラグ"] = merged["該当理由"].str.contains("PTS").astype(int)
    merged["出来高フラグ"] = merged["該当理由"].str.contains("出来高急増").astype(int)
    merged["値上率フラグ"] = merged["該当理由"].str.contains("値上がり率").astype(int)
    merged["高値フラグ"] = merged["該当理由"].str.contains("年初来高値").astype(int)
    merged["開示フラグ"] = merged["該当理由"].str.contains("適時開示").astype(int)

    merged = merged.sort_values(
        by=[
            "理由数",
            "PTSフラグ",
            "出来高フラグ",
            "値上率フラグ",
            "高値フラグ",
            "開示フラグ",
            "コード",
        ],
        ascending=[False, False, False, False, False, False, True],
    )

    return merged[COLUMNS].to_dict("records")


def main():
    return save_csv(
        collect(),
        "ai_final_candidates.csv",
        COLUMNS,
    )


if __name__ == "__main__":
    main()