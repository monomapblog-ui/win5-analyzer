"""WIN5詳細ページの日付・構造確認"""
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

    for idx in [0, 1, 2]:
        print(f"\n{'='*60}")
        print(f"win5.html?idx={idx}")
        resp = client.get(f"{BASE}/win5.html?idx={idx}")
        soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")

        # ページ全テキストから日付を探す
        text = soup.get_text(separator="\n")
        print("--- 日付っぽい行 ---")
        for line in text.splitlines():
            line = line.strip()
            if line and ("年" in line or "月" in line or "週" in line or "2024" in line or "2025" in line or "2026" in line):
                print(f"  {line[:60]}")

        # title・h1・h2・h3
        print("--- タイトル系タグ ---")
        for tag in soup.find_all(["title","h1","h2","h3","p"]):
            t = tag.get_text(strip=True)
            if t:
                print(f"  <{tag.name}>: {t[:60]}")

        # win5raceresult2テーブルの全行
        print("--- win5raceresult2 テーブル ---")
        table = soup.find("table", class_="win5raceresult2")
        if table:
            for i, row in enumerate(table.find_all("tr")):
                cells = row.find_all(["td","th"])
                texts = [c.get_text(strip=True)[:30] for c in cells]
                links = [a["href"] for c in cells for a in c.find_all("a", href=True)]
                print(f"  row[{i}]: {texts}")
                if links:
                    print(f"         links: {links}")

        # 払戻テーブル
        print("--- 払戻テーブル ---")
        for table in soup.find_all("table", class_="Win5_Table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["td","th"])
                print(f"  {[c.get_text(strip=True)[:30] for c in cells]}")
