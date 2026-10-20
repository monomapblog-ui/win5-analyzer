"""騎手IDからフルネームを取得できるか確認する(姓のみ問題の解決策調査用)。
db.netkeiba.comはEUC-JPエンコーディング。

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

JOCKEY_ID = "00894"
URL = f"https://db.netkeiba.com/jockey/{JOCKEY_ID}/"

with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
    resp = client.get(URL)

print(f"URL: {URL}")
print(f"ステータス: {resp.status_code}")

soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")

title = soup.find("title")
print(f"<title>: {title.get_text(strip=True) if title else None}")

name_el = soup.find(class_="Name")
if name_el:
    print(f"\nclass=Name のテキスト: {name_el.get_text(strip=True)!r}")
    print(f"\nclass=Name の生HTML:\n{str(name_el)[:800]}")
else:
    print("class=Name が見つからず")
