import time
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def fetch_html(url: str, retries: int = 3, sleep_seconds: int = 2) -> str:
    last_error = None

    for _ in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            return response.text

        except requests.RequestException as error:
            last_error = error
            time.sleep(sleep_seconds)

    raise RuntimeError(f"取得失敗: {url}") from last_error