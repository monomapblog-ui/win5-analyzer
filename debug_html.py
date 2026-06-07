"""レース結果テーブル All_Result_Table の列構造を確認"""
import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://race.netkeiba.com/top/win5.html",
}

race_id = "202605030211"
url = f"https://race.netkeiba.com/race/result.html?race_id={race_id}"

with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
    resp = client.get(url)

soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")
table = soup.find("table", id="All_Result_Table")

if table is None:
    print("All_Result_Table が見つかりません")
else:
    print(f"All_Result_Table: {len(table.find_all('tr'))} 行\n")
    for i, row in enumerate(table.find_all("tr")):
        cells = row.find_all(["td", "th"])
        texts = [c.get_text(strip=True)[:20] for c in cells]
        links = [a["href"][:60] for c in cells for a in c.find_all("a", href=True)][:2]
        print(f"row[{i:2d}] ({len(cells)}セル): {texts}")
        if links:
            print(f"        links: {links}")
