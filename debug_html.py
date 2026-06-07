"""レース結果ページのHTML構造確認"""
import re
import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://race.netkeiba.com/top/win5.html",
}

# 直近のWIN5レース（idx=1のデータから取得済み）
race_id = "202605030211"  # 東京11R 安田記念
url = f"https://race.netkeiba.com/race/result.html?race_id={race_id}"

print(f"URL: {url}")
with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
    resp = client.get(url)
print(f"ステータス: {resp.status_code}  長さ: {len(resp.text)}")

soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")

# 全テーブルのclass・id・行数を確認
print(f"\n全テーブル:")
for i, t in enumerate(soup.find_all("table")):
    rows = t.find_all("tr")
    print(f"  [{i}] id={t.get('id','')} class={t.get('class',[])} rows={len(rows)}")

# 最も行数が多いテーブル（レース結果テーブルのはず）の全行を表示
tables = soup.find_all("table")
if tables:
    main_table = max(tables, key=lambda t: len(t.find_all("tr")))
    print(f"\n最大テーブル (rows={len(main_table.find_all('tr'))}) の内容:")
    for i, row in enumerate(main_table.find_all("tr")):
        cells = row.find_all(["td", "th"])
        texts = [c.get_text(strip=True)[:15] for c in cells]
        links = [a["href"][:50] for c in cells for a in c.find_all("a", href=True)][:2]
        print(f"  row[{i:2d}] ({len(cells)}セル): {texts}")
        if links:
            print(f"          links: {links}")
