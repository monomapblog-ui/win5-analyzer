"""WIN5結果ページの構造確認"""
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

BASE = "https://race.netkeiba.com/top"

with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:

    # ① 過去結果一覧ページ
    print("="*60)
    print("① win5_results.html")
    resp = client.get(f"{BASE}/win5_results.html")
    print(f"ステータス: {resp.status_code}  長さ: {len(resp.text)}")
    soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")
    with open("debug_results.html", "w", encoding="utf-8") as f:
        f.write(soup.prettify())
    print("→ debug_results.html に保存")

    # テーブル構造
    for i, table in enumerate(soup.find_all("table")):
        rows = table.find_all("tr")
        print(f"  table[{i}] class={table.get('class',[])} rows={len(rows)}")
        for row in rows[:5]:
            cells = row.find_all(["td","th"])
            texts = [c.get_text(strip=True)[:20] for c in cells[:6]]
            links = [a["href"] for c in cells for a in c.find_all("a",href=True)][:3]
            if texts:
                print(f"    {texts}  links={links}")

    print()

    # ② 直近のWIN5詳細（idx=0）
    print("="*60)
    print("② win5.html?idx=0（直近）")
    resp2 = client.get(f"{BASE}/win5.html?idx=0")
    print(f"ステータス: {resp2.status_code}  長さ: {len(resp2.text)}")
    soup2 = BeautifulSoup(resp2.content, "lxml", from_encoding="euc-jp")
    with open("debug_detail.html", "w", encoding="utf-8") as f:
        f.write(soup2.prettify())
    print("→ debug_detail.html に保存")

    for i, table in enumerate(soup2.find_all("table")):
        rows = table.find_all("tr")
        print(f"  table[{i}] class={table.get('class',[])} rows={len(rows)}")
        for row in rows[:8]:
            cells = row.find_all(["td","th"])
            texts = [c.get_text(strip=True)[:25] for c in cells[:6]]
            links = [a["href"] for c in cells for a in c.find_all("a",href=True)][:3]
            if texts:
                print(f"    {texts}  links={links}")
