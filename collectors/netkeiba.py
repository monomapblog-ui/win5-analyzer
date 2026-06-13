"""netkeibaからWIN5結果・レース結果を収集

確認済みURL:
  WIN5過去一覧: https://race.netkeiba.com/top/win5_results.html
                → win5.html?date=YYYYMMDD 形式のリンク一覧
  WIN5詳細:     https://race.netkeiba.com/top/win5.html?date=YYYYMMDD
  レース結果:   https://race.netkeiba.com/race/result.html?race_id=RACEID
"""
import re
import time
import os
from datetime import date

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

DELAY       = float(os.getenv("REQUEST_DELAY_SECONDS", "2.0"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

BASE = "https://race.netkeiba.com/top"

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


# ─────────────────────────────────────────────
# HTTPクライアント
# ─────────────────────────────────────────────

def _get(url: str) -> httpx.Response:
    for attempt in range(MAX_RETRIES):
        time.sleep(DELAY)
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=30.0, follow_redirects=True)
            resp.raise_for_status()
            return resp
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = 2 ** (attempt + 1)
            print(f"    リトライ {attempt+1}/{MAX_RETRIES} ({wait}s): {e}")
            time.sleep(wait)
    raise RuntimeError(f"取得失敗: {url}")


# ─────────────────────────────────────────────
# WIN5 過去日付一覧
# ─────────────────────────────────────────────

def fetch_win5_dates(target_years: list[int] | None = None) -> list[str]:
    """
    win5_results.html?year=YYYY から各年のWIN5日付リストを取得する。
    返り値: ['20240101', '20240108', ...] （古い順）
    target_years 指定時はその年のみ返す。

    ページ構造:
      <select name="year"> に 2011〜現在の年が並んでいる
      <form action="win5_results.html" method="get"> で年別切り替え
      各リンクは win5.html?date=YYYYMMDD 形式
    """
    years_to_fetch = target_years or [date.today().year]
    all_dates = []

    for year in years_to_fetch:
        url = f"{BASE}/win5_results.html?year={year}"
        resp = _get(url)
        soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")

        for a in soup.find_all("a", href=True):
            m = re.search(r"win5\.html\?date=(\d{8})", a["href"])
            if m:
                all_dates.append(m.group(1))

    # 重複除去・古い順ソート
    return sorted(set(all_dates))


# ─────────────────────────────────────────────
# WIN5 詳細（1日分）
# ─────────────────────────────────────────────

def fetch_win5_by_date(date_str: str) -> dict | None:
    """
    win5.html?date=YYYYMMDD から1開催分のデータを取得する。

    返り値:
      held_date   : date
      slots       : list[dict]
        slot_number      : 1〜5
        race_id          : str (12桁)
        venue_race_name  : str
        winner_horse_name: str
        winner_horse_id  : str
      payout      : int | None
      unit_count  : int | None
    """
    url = f"{BASE}/win5.html?date={date_str}"
    resp = _get(url)
    soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")

    # データなし判定
    no_data = soup.find("p", string=re.compile(r"win5データはありません"))
    if no_data:
        return None

    held_date = _parse_date_from_title(soup)
    if held_date is None:
        return None

    # 対象レーステーブル（win5raceresult2）
    table = soup.find("table", class_="win5raceresult2")
    if table is None:
        return None

    rows = table.find_all("tr")
    # row[0]: ヘッダ（1〜5レース）
    # row[1]: レース名 + race_idリンク
    # row[2]: 勝ち馬名 + horse_idリンク
    # row[3]: 単勝人気（空欄 → レース結果ページから取得）
    # row[4]: 残り票数

    race_row   = rows[1] if len(rows) > 1 else None
    winner_row = rows[2] if len(rows) > 2 else None

    slots = []
    if race_row and winner_row:
        race_cells   = race_row.find_all(["td", "th"])
        winner_cells = winner_row.find_all(["td", "th"])

        for slot_num in range(1, 6):
            rc = race_cells[slot_num]   if len(race_cells)   > slot_num else None
            wc = winner_cells[slot_num] if len(winner_cells) > slot_num else None

            # race_id
            race_id = None
            if rc:
                a = rc.find("a", href=True)
                if a:
                    m = re.search(r"race_id=(\d{12})", a["href"])
                    if m:
                        race_id = m.group(1)

            # 勝ち馬名
            winner_name = wc.get_text(strip=True) if wc else None

            # 勝ち馬horse_id
            winner_horse_id = None
            if wc:
                a = wc.find("a", href=True)
                if a:
                    m = re.search(r"/horse/([^/?]+)", a["href"])
                    if m:
                        winner_horse_id = m.group(1)

            slots.append({
                "slot_number":       slot_num,
                "race_id":           race_id,
                "venue_race_name":   rc.get_text(strip=True) if rc else None,
                "winner_horse_name": winner_name,
                "winner_horse_id":   winner_horse_id,
                "winner_popularity": None,  # レース結果ページで補完
            })

    # 払戻・的中票数
    payout     = None
    unit_count = None
    for table_w in soup.find_all("table", class_="Win5_Table"):
        for row in table_w.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            key = cells[0].get_text(strip=True)
            val = cells[1].get_text(strip=True)
            if "払戻金" in key:
                payout = _parse_money(val)
            elif "的中票数" in key:
                unit_count = _parse_int(val)

    return {
        "held_date":  held_date,
        "slots":      slots,
        "payout":     payout,
        "unit_count": unit_count,
    }


# ─────────────────────────────────────────────
# レース結果（勝ち馬の人気取得）
# ─────────────────────────────────────────────

def fetch_race_result(race_id: str) -> dict:
    """
    レース結果ページから全出走馬の着順・人気・オッズを取得する。
    URL: https://race.netkeiba.com/race/result.html?race_id=RACEID

    返り値:
      race_id  : str
      entries  : list[dict]
        finish_position, frame_number, horse_number,
        horse_name, horse_id, popularity, odds
    """
    url = f"https://race.netkeiba.com/race/result.html?race_id={race_id}"
    resp = _get(url)
    soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")

    entries = []

    # レース結果テーブル: class="RaceTable01" または "race_table_01"
    table = soup.find("table", class_=re.compile(r"RaceTable01|race_table_01"))
    if table is None:
        table = soup.find("table", id=re.compile(r"result|Result"))
    if table is None:
        # フォールバック: tbody内の最初のテーブル
        for t in soup.find_all("table"):
            rows = t.find_all("tr")
            if len(rows) > 3:
                table = t
                break

    if table is None:
        return {"race_id": race_id, "entries": entries}

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 5:
            continue

        finish_pos = _parse_int(cells[0].get_text())
        if finish_pos is None:
            continue

        # horse_id
        horse_id   = None
        for cell in cells:
            a = cell.find("a", href=re.compile(r"/horse/"))
            if a:
                m = re.search(r"/horse/([^/?]+)", a["href"])
                if m:
                    horse_id = m.group(1)
                break

        # 馬名
        horse_name = None
        for cell in cells:
            a = cell.find("a", href=re.compile(r"/horse/"))
            if a:
                horse_name = a.get_text(strip=True)
                break

        # 人気・オッズはtable内の列順に依存
        # 一般的な列順: 着順|枠|馬番|馬名|性齢|斤量|騎手|タイム|着差|人気|単勝
        popularity = _parse_int(cells[9].get_text())  if len(cells) > 9  else None
        odds       = _parse_float(cells[10].get_text()) if len(cells) > 10 else None

        entries.append({
            "finish_position": finish_pos,
            "frame_number":    _parse_int(cells[1].get_text()) if len(cells) > 1 else None,
            "horse_number":    _parse_int(cells[2].get_text()) if len(cells) > 2 else None,
            "horse_name":      horse_name,
            "horse_id":        horse_id,
            "popularity":      popularity,
            "odds":            odds,
        })

    return {"race_id": race_id, "entries": entries}


# ─────────────────────────────────────────────
# レース特徴量（難易度分析用）
# ─────────────────────────────────────────────

def fetch_race_features(race_id: str) -> dict:
    """
    レース結果ページから特徴量を抽出する。
    返り値:
      field_size, course_type, distance, track_condition,
      fav1_odds, fav2_odds, winner_odds, winner_pop, entries
    """
    url = f"https://race.netkeiba.com/race/result.html?race_id={race_id}"
    resp = _get(url)
    soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")

    # ── コース・距離・馬場 ──
    course_type     = None
    distance        = None
    track_condition = None

    race_data = soup.find("div", class_="RaceData01")
    if race_data:
        text = race_data.get_text(" ", strip=True)
        # 例: "芝2400m / 良" or "ダ1600m / 稍重"
        m = re.search(r"(芝|ダート|ダ|障害)([\d,]+)m", text)
        if m:
            raw = m.group(1)
            course_type = "芝" if raw == "芝" else ("ダート" if raw in ("ダ", "ダート") else "障害")
            distance = int(m.group(2).replace(",", ""))
        for cond in ["良", "稍重", "重", "不良"]:
            if cond in text:
                track_condition = cond
                break

    # ── 出走馬・オッズ ──
    entries = []
    table = soup.find("table", class_=re.compile(r"RaceTable01|race_table_01"))
    if table is None:
        for t in soup.find_all("table"):
            if len(t.find_all("tr")) > 3:
                table = t
                break

    if table:
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 5:
                continue
            finish_pos = _parse_int(cells[0].get_text())
            if finish_pos is None:
                continue
            popularity = _parse_int(cells[9].get_text())  if len(cells) > 9  else None
            odds       = _parse_float(cells[10].get_text()) if len(cells) > 10 else None
            entries.append({"finish_pos": finish_pos, "popularity": popularity, "odds": odds})

    field_size = len(entries)
    fav1_odds  = next((e["odds"] for e in entries if e["popularity"] == 1), None)
    fav2_odds  = next((e["odds"] for e in entries if e["popularity"] == 2), None)
    winner     = next((e for e in entries if e["finish_pos"] == 1), None)
    winner_odds = winner["odds"]    if winner else None
    winner_pop  = winner["popularity"] if winner else None

    return {
        "field_size":      field_size,
        "course_type":     course_type,
        "distance":        distance,
        "track_condition": track_condition,
        "fav1_odds":       fav1_odds,
        "fav2_odds":       fav2_odds,
        "winner_odds":     winner_odds,
        "winner_pop":      winner_pop,
    }


# ─────────────────────────────────────────────
# 内部ヘルパー
# ─────────────────────────────────────────────

def _parse_date_from_title(soup) -> date | None:
    """<title>WIN5対象レース | 2026年6月6日 ... から日付を抽出"""
    title = soup.find("title")
    if title:
        m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", title.get_text())
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
    return None


def _parse_money(text: str) -> int | None:
    # "315万9870円" → 3159870、"1,234,567円" → 1234567
    text = text.replace(",", "")
    # 万円単位
    m = re.search(r"(\d+)万(\d{1,4})円", text)
    if m:
        return int(m.group(1)) * 10000 + int(m.group(2))
    m = re.search(r"(\d+)万円", text)
    if m:
        return int(m.group(1)) * 10000
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _parse_int(text: str) -> int | None:
    if text is None:
        return None
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else None


def _parse_float(text: str) -> float | None:
    if text is None:
        return None
    s = re.sub(r"[^\d.]", "", str(text))
    try:
        return float(s) if s else None
    except ValueError:
        return None
