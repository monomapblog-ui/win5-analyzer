"""古いnetkeibaレース結果ページで、騎手名セルの生HTML構造を確認する。
騎手名が途中で切れる問題(「ルメール」→「ルメー」等)の原因調査用。

使い方:
  python debug_old_jockey.py
"""
import sqlite3

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

conn = sqlite3.connect("win5.db")
cur = conn.cursor()
cur.execute(
    """
    select s.race_id_str, s.winner_jockey, s.winner_horse_name, e.held_date
    from win5_slots s
    join win5_events e on e.id = s.event_id
    where e.held_date < '2019-01-01' and s.race_id_str is not null
    limit 3
    """
)
rows = cur.fetchall()
print(f"対象レース: {len(rows)}件")
for race_id_str, winner_jockey, winner_horse_name, held_date in rows:
    print(f"\n{'='*70}")
    print(f"held_date={held_date} race_id={race_id_str} 保存済みjockey={winner_jockey!r} horse={winner_horse_name!r}")

    url = f"https://race.netkeiba.com/race/result.html?race_id={race_id_str}"
    print(f"URL: {url}")
    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        resp = client.get(url)
    print(f"ステータス: {resp.status_code}  長さ: {len(resp.text)}")

    soup = BeautifulSoup(resp.content, "lxml", from_encoding="utf-8")

    print("全テーブル:")
    for i, t in enumerate(soup.find_all("table")):
        rows_in_table = t.find_all("tr")
        print(f"  [{i}] id={t.get('id','')} class={t.get('class',[])} rows={len(rows_in_table)}")

    import re as _re
    table = soup.find("table", class_=_re.compile(r"RaceTable01|race_table_01"))
    if table is None:
        print("  → RaceTable01/race_table_01 クラスのテーブルが見つからず")
        continue

    print("\n  勝ち馬(1着)の行、全セルの中身:")
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 5:
            continue
        finish_text = cells[0].get_text(strip=True)
        if finish_text != "1":
            continue
        for idx, cell in enumerate(cells):
            text = cell.get_text(strip=True)
            print(f"    cell[{idx}] text={text!r}")
            print(f"             html={str(cell)[:200]}")
        break
