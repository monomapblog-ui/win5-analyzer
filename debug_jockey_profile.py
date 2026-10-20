"""騎手IDからフルネームを取得できるか確認する(姓のみ問題の解決策調査用)。

使い方:
  python debug_jockey_profile.py
"""
import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# 2011-04-24 201108030210 で「小牧」(= 小牧太のはず)として出てきた騎手ID
JOCKEY_ID = "00894"

CANDIDATE_URLS = [
    f"https://db.netkeiba.com/jockey/{JOCKEY_ID}/",
    f"https://db.netkeiba.com/jockey/profile/{JOCKEY_ID}/",
    f"https://db.netkeiba.com/jockey/result/recent/{JOCKEY_ID}/",
]

with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
    for url in CANDIDATE_URLS:
        print(f"\n{'='*70}")
        print(f"URL: {url}")
        try:
            resp = client.get(url)
        except Exception as e:
            print(f"  取得失敗: {e}")
            continue
        print(f"ステータス: {resp.status_code}  最終URL: {resp.url}")
        if resp.status_code != 200:
            continue

        soup = BeautifulSoup(resp.content, "lxml", from_encoding="utf-8")

        title = soup.find("title")
        print(f"  <title>: {title.get_text(strip=True) if title else None}")

        h1 = soup.find("h1")
        print(f"  <h1>: {h1.get_text(strip=True) if h1 else None}")

        # それらしいクラス名をいくつか試す
        for cls in ["Name", "DB_Name", "db_name", "Jockey_Name", "ProfileName"]:
            el = soup.find(class_=cls)
            if el:
                print(f"  class={cls}: {el.get_text(strip=True)}")
