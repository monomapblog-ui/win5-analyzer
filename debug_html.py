"""オッズページのHTML構造確認"""
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

race_id = "202605030211"  # 安田記念

with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
    for url in [
        f"https://race.netkeiba.com/odds/index.html?race_id={race_id}&type=b1",
        f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}",
    ]:
        print(f"\n{'='*60}")
        print(f"URL: {url}")
        resp = client.get(url)
        print(f"ステータス: {resp.status_code}  長さ: {len(resp.text)}")
        soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")

        print("全テーブル:")
        for i, t in enumerate(soup.find_all("table")):
            rows = t.find_all("tr")
            print(f"  [{i}] id={t.get('id','')} class={t.get('class',[])} rows={len(rows)}")

        # 最大テーブルの最初の5行
        tables = soup.find_all("table")
        if tables:
            best = max(tables, key=lambda t: len(t.find_all("tr")))
            print(f"\n最大テーブルの内容 (id={best.get('id','')}):")
            for i, row in enumerate(best.find_all("tr")[:6]):
                cells = row.find_all(["td","th"])
                print(f"  row[{i}]: {[c.get_text(strip=True)[:15] for c in cells[:8]]}")
