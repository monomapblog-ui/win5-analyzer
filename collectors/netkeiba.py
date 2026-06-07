"""netkeibaからWIN5結果・レース結果・馬プロフィールを収集

主要URL:
  WIN5結果一覧: https://db.netkeiba.com/?pid=win5_list&year=YYYY
  WIN5詳細:     https://race.netkeiba.com/top/win5.html?kaisai_date=YYYYMMDD
  レース結果:   https://db.netkeiba.com/race/RACEID/   (RACEID例: 202401010101)
  出馬表:       https://race.netkeiba.com/race/shutuba.html?race_id=RACEID
  馬情報:       https://db.netkeiba.com/horse/HORSEID/
"""
import re
from datetime import date
from bs4 import BeautifulSoup

from utils.http import RateLimitedClient

NETKEIBA_DB   = "https://db.netkeiba.com"
NETKEIBA_RACE = "https://race.netkeiba.com"


# ─────────────────────────────────────────────
# WIN5 一覧
# ─────────────────────────────────────────────

async def fetch_win5_list(year: int) -> list[dict]:
    """
    指定年のWIN5開催一覧を取得する。

    返り値の各要素:
      held_date   : date
      race_ids    : list[str]  # 対象5レースのrace_id（順番通り）
      payout      : int | None # 払戻金（円）
      unit_count  : int | None # 的中口数
    """
    url = f"{NETKEIBA_DB}/?pid=win5_list&year={year}"
    async with RateLimitedClient() as client:
        resp = await client.get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    results = []
    # netkeibaのWIN5一覧テーブル: class="nk_tb_common"
    table = soup.find("table", class_=re.compile(r"win5|nk_tb_common"))
    if table is None:
        # フォールバック: ページ内の最初のテーブル
        table = soup.find("table")
    if table is None:
        return results

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        held_date = _parse_date(cells[0].get_text(strip=True))
        if not held_date:
            continue

        # 対象5レースのリンクを抽出
        race_ids = []
        for a in cells[1].find_all("a", href=True):
            rid = _extract_race_id(a["href"])
            if rid:
                race_ids.append(rid)

        payout    = _parse_money(cells[2].get_text(strip=True)) if len(cells) > 2 else None
        unit_count = _parse_int(cells[3].get_text(strip=True)) if len(cells) > 3 else None

        results.append({
            "held_date":  held_date,
            "race_ids":   race_ids,
            "payout":     payout,
            "unit_count": unit_count,
        })

    return results


# ─────────────────────────────────────────────
# WIN5 詳細ページ（1開催分の5レース + 払戻）
# ─────────────────────────────────────────────

async def fetch_win5_detail(held_date: date) -> dict:
    """
    WIN5詳細ページから対象5レース・勝ち馬人気・払戻を取得する。

    返り値:
      held_date   : date
      slots       : list[dict]  # slot_number(1-5), race_id, venue, race_name,
                                #   winner_horse_name, winner_popularity
      payout      : int | None
      unit_count  : int | None
    """
    date_str = held_date.strftime("%Y%m%d")
    url = f"{NETKEIBA_RACE}/top/win5.html?kaisai_date={date_str}"
    async with RateLimitedClient() as client:
        resp = await client.get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    slots = []
    # WIN5詳細: 各レースブロックは .Win5RaceList または ul.Win5RaceList li など
    race_blocks = soup.select(".Win5Race, .win5_race, li.Win5RaceList")
    if not race_blocks:
        # フォールバック: テーブル行
        race_blocks = soup.select("table.win5_table tr, table tr")

    for i, block in enumerate(race_blocks[:5], start=1):
        text = block.get_text(separator=" ", strip=True)
        race_id = None
        for a in block.find_all("a", href=True):
            rid = _extract_race_id(a["href"])
            if rid:
                race_id = rid
                break

        # 会場名・レース名
        venue     = _extract_venue(block)
        race_name = _extract_race_name(block)

        # 勝ち馬・人気
        winner_name = None
        winner_pop  = None
        winner_tag  = block.find(class_=re.compile(r"winner|Win|horse", re.I))
        if winner_tag:
            winner_name = winner_tag.get_text(strip=True)
        pop_match = re.search(r"(\d+)番人気", text)
        if pop_match:
            winner_pop = int(pop_match.group(1))

        slots.append({
            "slot_number":        i,
            "race_id":            race_id,
            "venue":              venue,
            "race_name":          race_name,
            "winner_horse_name":  winner_name,
            "winner_popularity":  winner_pop,
        })

    # 払戻・的中口数
    payout_text = soup.get_text()
    payout     = None
    unit_count = None
    pm = re.search(r"払戻金[^\d]*([\d,]+)円", payout_text)
    if pm:
        payout = _parse_money(pm.group(1))
    um = re.search(r"的中口数[^\d]*(\d+)", payout_text)
    if um:
        unit_count = int(um.group(1))

    return {
        "held_date":  held_date,
        "slots":      slots,
        "payout":     payout,
        "unit_count": unit_count,
    }


# ─────────────────────────────────────────────
# レース結果（着順・人気・オッズ）
# ─────────────────────────────────────────────

async def fetch_race_result(race_id: str) -> dict:
    """
    レース結果ページから全出走馬の着順・人気・オッズを取得する。

    返り値:
      race_id  : str
      entries  : list[dict]  # finish_position, frame_number, horse_number,
                             #   horse_name, horse_id, popularity, odds
    """
    url = f"{NETKEIBA_DB}/race/{race_id}/"
    async with RateLimitedClient() as client:
        resp = await client.get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    entries = []
    # netkeibaレース結果テーブル: class="race_table_01 nk_tb_common"
    table = soup.find("table", class_=re.compile(r"race_table_01|race_result"))
    if table is None:
        table = soup.find("table")
    if table is None:
        return {"race_id": race_id, "entries": entries}

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 11:
            continue

        finish_pos = _parse_int(cells[0].get_text())
        if finish_pos is None:
            continue  # ヘッダ行・除外行をスキップ

        # horse_id を href から抽出
        horse_id   = None
        horse_link = cells[3].find("a", href=True)
        if horse_link:
            m = re.search(r"/horse/([^/]+)/?", horse_link["href"])
            if m:
                horse_id = m.group(1)

        entries.append({
            "finish_position": finish_pos,
            "frame_number":    _parse_int(cells[1].get_text()),
            "horse_number":    _parse_int(cells[2].get_text()),
            "horse_name":      cells[3].get_text(strip=True),
            "horse_id":        horse_id,
            "popularity":      _parse_int(cells[10].get_text()),
            "odds":            _parse_float(cells[9].get_text()),
        })

    return {"race_id": race_id, "entries": entries}


# ─────────────────────────────────────────────
# 出馬表（レース前の情報）
# ─────────────────────────────────────────────

async def fetch_shutuba(race_id: str) -> dict:
    """
    出馬表から馬番・枠番・馬名・馬IDを取得する（レース前分析用）。

    返り値:
      race_id  : str
      race_info: dict  # venue, race_name, date, course, distance
      entries  : list[dict]  # frame_number, horse_number, horse_name, horse_id
    """
    url = f"{NETKEIBA_RACE}/race/shutuba.html?race_id={race_id}"
    async with RateLimitedClient() as client:
        resp = await client.get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    # レース情報
    race_info = {}
    title_tag = soup.find(class_=re.compile(r"RaceTitle|race_title"))
    if title_tag:
        race_info["race_name"] = title_tag.get_text(strip=True)
    data_tag = soup.find(class_=re.compile(r"RaceData|race_data"))
    if data_tag:
        text = data_tag.get_text()
        dm = re.search(r"(\d+)m", text)
        if dm:
            race_info["distance"] = int(dm.group(1))
        race_info["course"] = "芝" if "芝" in text else "ダート" if "ダート" in text else None

    entries = []
    table = soup.find("table", class_=re.compile(r"Shutuba|shutuba"))
    if table is None:
        table = soup.find("table")
    if table:
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            horse_id   = None
            horse_link = cells[3].find("a", href=True) if len(cells) > 3 else None
            if horse_link:
                m = re.search(r"/horse/([^/]+)/?", horse_link["href"])
                if m:
                    horse_id = m.group(1)
            entries.append({
                "frame_number": _parse_int(cells[0].get_text()),
                "horse_number": _parse_int(cells[1].get_text()),
                "horse_name":   cells[3].get_text(strip=True) if len(cells) > 3 else None,
                "horse_id":     horse_id,
            })

    return {"race_id": race_id, "race_info": race_info, "entries": entries}


# ─────────────────────────────────────────────
# 馬プロフィール
# ─────────────────────────────────────────────

async def fetch_horse_profile(horse_id: str) -> dict:
    """
    馬プロフィールページから基本情報を取得する。

    返り値:
      horse_id   : str
      name       : str | None
      sex        : str | None
      birth_year : int | None
    """
    url = f"{NETKEIBA_DB}/horse/{horse_id}/"
    async with RateLimitedClient() as client:
        resp = await client.get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    profile = {"horse_id": horse_id}

    name_tag = soup.find("h1", class_=re.compile(r"horse_title|HorseName"))
    if name_tag:
        profile["name"] = name_tag.get_text(strip=True)

    dl = soup.find("dl", class_=re.compile(r"db_prof_table|HorseData"))
    if dl:
        for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
            key = dt.get_text(strip=True)
            val = dd.get_text(strip=True)
            if "生年月日" in key or "生年" in key:
                m = re.search(r"(\d{4})", val)
                if m:
                    profile["birth_year"] = int(m.group(1))
            elif "性" in key:
                profile["sex"] = val[:2]

    return profile


# ─────────────────────────────────────────────
# 内部ヘルパー
# ─────────────────────────────────────────────

def _parse_date(text: str) -> date | None:
    m = re.search(r"(\d{4})[年/\-\.](\d{1,2})[月/\-\.](\d{1,2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _parse_money(text: str) -> int | None:
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


def _extract_race_id(href: str) -> str | None:
    # race_id は12桁の数字: 202401010101
    m = re.search(r"race_id=(\d{12})", href)
    if m:
        return m.group(1)
    m = re.search(r"/race/(\d{12})/?", href)
    if m:
        return m.group(1)
    return None


def _extract_venue(tag) -> str | None:
    venue_tag = tag.find(class_=re.compile(r"venue|place|Venue", re.I))
    if venue_tag:
        return venue_tag.get_text(strip=True)
    text = tag.get_text()
    venues = ["札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"]
    for v in venues:
        if v in text:
            return v
    return None


def _extract_race_name(tag) -> str | None:
    name_tag = tag.find(class_=re.compile(r"race_name|RaceName|name", re.I))
    if name_tag:
        return name_tag.get_text(strip=True)
    return None
