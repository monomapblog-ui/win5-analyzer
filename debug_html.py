"""HTMLの実際の構造を確認するデバッグスクリプト"""
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
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

urls = [
    "https://www.jra.go.jp/keiba/overseas/win5/",
    "https://race.netkeiba.com/top/win5.html",
    "https://db.netkeiba.com/?pid=win5_list&year=2024",
]

for url in urls:
    print(f"\n{'='*60}")
    print(f"URL: {url}")
    try:
        with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
            # まずトップページを取得してcookieを得る
            client.get("https://db.netkeiba.com/")
            resp = client.get(url)
        print(f"ステータス: {resp.status_code}")
        print(f"Content-Length: {len(resp.text)}")
        print(f"最初の200文字:\n{resp.text[:200]}")

        soup = BeautifulSoup(resp.text, "lxml")
        tables = soup.find_all("table")
        print(f"テーブル数: {len(tables)}")

        # WIN5っぽいリンクを探す
        for a in soup.find_all("a", href=True)[:30]:
            href = a["href"]
            if "win5" in href.lower() or "race_id" in href.lower():
                print(f"  リンク: {a.get_text(strip=True)[:30]} -> {href}")

    except Exception as e:
        print(f"エラー: {e}")
