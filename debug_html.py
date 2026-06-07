"""過去WIN5へのナビゲーション構造を確認"""
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

    # ① win5.html の全リンクを確認
    print("="*60)
    print("① win5.html の全リンク")
    resp = client.get(f"{BASE}/win5.html")
    soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)[:30]
        if text or "win5" in href.lower() or "kaisai" in href.lower():
            print(f"  '{text}' -> {href}")

    # ② win5_results.html の全リンクを確認
    print("\n" + "="*60)
    print("② win5_results.html の全リンク（上位50件）")
    resp2 = client.get(f"{BASE}/win5_results.html")
    soup2 = BeautifulSoup(resp2.content, "lxml", from_encoding="euc-jp")
    links = soup2.find_all("a", href=True)
    print(f"総リンク数: {len(links)}")
    for a in links[:50]:
        href = a["href"]
        text = a.get_text(strip=True)[:30]
        print(f"  '{text}' -> {href}")

    # ③ kaisai_date パラメータで直接アクセス（例: 2024年1月6日）
    print("\n" + "="*60)
    print("③ kaisai_date=20240106 で直接アクセス")
    resp3 = client.get(f"{BASE}/win5.html?kaisai_date=20240106")
    soup3 = BeautifulSoup(resp3.content, "lxml", from_encoding="euc-jp")
    title = soup3.find("title")
    print(f"title: {title.get_text() if title else 'なし'}")
    table = soup3.find("table", class_="win5raceresult2")
    if table:
        for row in table.find_all("tr"):
            cells = row.find_all(["td","th"])
            texts = [c.get_text(strip=True)[:25] for c in cells]
            links_in_row = [a["href"] for c in cells for a in c.find_all("a", href=True)]
            print(f"  {texts}")
            if links_in_row:
                print(f"    links: {links_in_row}")
    else:
        p = soup3.find("p")
        print(f"テーブルなし。p: {p.get_text() if p else 'なし'}")
