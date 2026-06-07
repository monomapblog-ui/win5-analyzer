"""win5_results.htmlの年パラメータ・ページネーション確認"""
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

BASE = "https://race.netkeiba.com/top"

with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:

    # 年パラメータのバリエーションを試す
    test_urls = [
        f"{BASE}/win5_results.html",
        f"{BASE}/win5_results.html?year=2024",
        f"{BASE}/win5_results.html?year=2021",
    ]

    for url in test_urls:
        print(f"\n{'='*60}")
        print(f"URL: {url}")
        resp = client.get(url)
        print(f"ステータス: {resp.status_code}  長さ: {len(resp.text)}")
        soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")

        # WIN5日付リンクを全抽出
        date_links = []
        for a in soup.find_all("a", href=True):
            m = re.search(r"win5\.html\?date=(\d{8})", a["href"])
            if m:
                date_links.append(m.group(1))

        print(f"WIN5日付リンク数: {len(date_links)}")
        if date_links:
            print(f"  最古: {date_links[-1]}  最新: {date_links[0]}")

        # ページネーション・年セレクタを探す
        print("ページネーション・年選択っぽい要素:")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if any(k in href for k in ["page=", "year=", "p=", "next", "prev"]):
                print(f"  '{text}' -> {href}")
        for sel in soup.find_all("select"):
            print(f"  <select name={sel.get('name','')}>: {[o.get('value') for o in sel.find_all('option')]}")
        for form in soup.find_all("form"):
            print(f"  <form action={form.get('action','')} method={form.get('method','')}>")
