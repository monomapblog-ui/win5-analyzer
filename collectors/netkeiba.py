"""netkeibaからWIN5結果・レース結果・馬プロフィールを収集（同期版）

主要URL:
  WIN5結果一覧: https://db.netkeiba.com/?pid=win5_list&year=YYYY
  WIN5詳細:     https://race.netkeiba.com/top/win5.html?kaisai_date=YYYYMMDD
  レース結果:   https://db.netkeiba.com/race/RACEID/
  出馬表:       https://race.netkeiba.com/race/shutuba.html?race_id=RACEID
  馬情報:       https://db.netkeiba.com/horse/HORSEID/
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

NETKEIBA_DB   = "https://db.netkeiba.com"
NETKEIBA_RACE = "https://race.netkeiba.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


def _get(url: str) -> httpx.Response:
    """レート制限・リトライ付き同期GETリクエスト"""
    for attempt in range(MAX_RETRIES):
        time.sleep(DELAY)
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=30.0, follow_redirects=True)
            if resp.status_code == 200:
                return resp
            if resp.status_code == 403:
                raise httpx.HTTPStatusError(
                    f"403 Forbidden: {url}", request=resp.request, response=resp
                )
            resp.raise_for_status()
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = 2 ** (attempt + 1)
            print(f"    リトライ {attempt+1}/{MAX_RETRIES} ({wait}s待機): {e}")
            time.sleep(wait)
    raise RuntimeError(f"取得失敗: {url}")


# ─────────────────────────────────────────────
# WIN5 一覧
# ─────────────────────────────────────────────

def fetch_win5_list(year: int) -> list[dict]:
    """
    指定年のWIN5開催一覧を取得する。

    返り値の各要素:
      held_date  : date
      race_ids   : list[str]  対象5レースのrace_id
      payout     : int | None 払戻金（円）
      unit_count : int | None 的中口数
    """
    url = f"{NETKEIBA_DB}/?pid=win5_list&year={year}"
    resp = _get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    results = []
    table = soup.find("table", class_=re.compile(r"win5|nk_tb_common"))
    if table is None:
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

        race_ids = []
        for a in cells[1].find_all("a", href=True):
            rid = _extract_race_id(a["href"])
            if rid:
                race_ids.append(rid)

        payout     = _parse_money(cells[2].get_text(strip=True)) if len(cells) > 2 else None
        unit_count = _parse_int(cells[3].get_text(strip=True))   if len(cells) > 3 else None

        results.append({
            "held_date":  held_date,
            "race_ids":   race_ids,
            "payout":     payout,
            "unit_count": unit_count,
        })

    return results


# ─────────────────────────────────────────────
# WIN5 詳細（1開催分の5レース + 払戻）
# ─────────────────────────────────────────────

def fetch_win5_detail(held_date: date) -> dict:
    """
    WIN5詳細ページから対象5レース・勝ち馬人気・払戻を取得する。
    """
    date_str = held_date.strftime("%Y%m%d")
    url = f"{NETKEIBA_RACE}/top/win5.html?kaisai_date={date_str}"
    resp = _get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    slots = []
    race_blocks = soup.select(".Win5Race, .win5_race, li.Win5RaceList")
    if not race_blocks:
        race_blocks = soup.select("table.win5_table tr, table tr")

    for i, block in enumerate(race_blocks[:5], start=1):
        text     = block.get_text(separator=" ", strip=True)
        race_id  = None
        for a in block.find_all("a", href=True):
            rid = _extract_race_id(a["href"])
            if rid:
                race_id = rid
                break

        venue     = _extract_venue(block)
        race_name = _extract_race_name(block)

        winner_name = None
        winner_pop  = None
        winner_tag  = block.find(class_=re.compile(r"winner|Win|horse", re.I))
        if winner_tag:
            winner_name = winner_tag.get_text(strip=True)
        pop_match = re.search(r"(\d+)番人気", text)
        if pop_match:
            winner_pop = int(pop_match.group(1))

        slots.append({
            "slot_number":       i,
            "race_id":           race_id,
            "venue":             venue,
            "race_name":         race_name,
            "winner_horse_name": winner_name,
            "winner_popularity": winner_pop,
        })

    payout_text = soup.get_text()
    payout      = None
    unit_count  = None
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
# レース結果
# ─────────────────────────────────────────────

def fetch_race_result(race_id: str) -> dict:
    """
    レース結果ページから全出走馬の着順・人気・オッズを取得する。
    """
    url = f"{NETKEIBA_DB}/race/{race_id}/"
    resp = _get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    entries = []
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
            continue

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
# 馬プロフィール
# ─────────────────────────────────────────────

def fetch_horse_profile(horse_id: str) -> dict:
    url = f"{NETKEIBA_DB}/horse/{horse_id}/"
    resp = _get(url)
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
            if "生年月日" in key:
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
    for v in ["札幌","函館","福島","新潟","東京","中山","中京","京都","阪神","小倉"]:
        if v in text:
            return v
    return None


def _extract_race_name(tag) -> str | None:
    name_tag = tag.find(class_=re.compile(r"race_name|RaceName|name", re.I))
    if name_tag:
        return name_tag.get_text(strip=True)
    return None
