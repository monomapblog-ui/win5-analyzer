"""HTMLの実際の構造を確認するデバッグスクリプト

使い方:
  python debug_html.py
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

url = "https://db.netkeiba.com/?pid=win5_list&year=2024"
print(f"取得中: {url}")
resp = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
print(f"ステータス: {resp.status_code}")
print(f"Content-Type: {resp.headers.get('content-type')}")

# HTMLをファイルに保存
with open("debug_win5_list.html", "w", encoding=resp.encoding or "utf-8", errors="replace") as f:
    f.write(resp.text)
print("debug_win5_list.html に保存しました")

# テーブルを全部列挙
soup = BeautifulSoup(resp.text, "lxml")
tables = soup.find_all("table")
print(f"\nテーブル数: {len(tables)}")
for i, t in enumerate(tables):
    cls = t.get("class", [])
    rows = t.find_all("tr")
    print(f"\n  table[{i}] class={cls} rows={len(rows)}")
    for j, row in enumerate(rows[:3]):  # 最初の3行だけ表示
        cells = row.find_all(["td", "th"])
        print(f"    row[{j}]: {len(cells)}セル")
        for k, cell in enumerate(cells[:5]):
            text = cell.get_text(strip=True)[:40]
            links = [a.get("href","") for a in cell.find_all("a")]
            print(f"      cell[{k}]: '{text}' links={links}")

# divも確認
print("\n--- 主要div ---")
for div in soup.find_all("div", class_=True)[:20]:
    cls = div.get("class", [])
    text = div.get_text(strip=True)[:50]
    print(f"  div class={cls}: '{text}'")
