"""netkeibaからレース結果・馬プロフィール・WIN5払戻を収集"""
import re
from datetime import date
from bs4 import BeautifulSoup
from utils.http import RateLimitedClient

NETKEIBA_BASE = "https://db.netkeiba.com"


async def fetch_win5_results(year: int) -> list[dict]:
    """指定年のWIN5払戻一覧を取得する"""
    url = f"{NETKEIBA_BASE}/?pid=win5_list&year={year}"
    async with RateLimitedClient() as client:
        resp = await client.get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    results = []
    for row in soup.select("table.win5_table tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        held_date = _parse_date(cells[0].get_text(strip=True))
        payout = _parse_payout(cells[2].get_text(strip=True))
        unit_count = _int(cells[3].get_text())
        if held_date:
            results.append({
                "held_date": held_date,
                "payout": payout,
                "unit_count": unit_count,
            })
    return results


async def fetch_race_result(race_id: str) -> dict:
    """レース結果（着順・人気・馬名）を取得する"""
    url = f"{NETKEIBA_BASE}/race/{race_id}/"
    async with RateLimitedClient() as client:
        resp = await client.get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    entries = []
    for row in soup.select("table.race_table_01 tr"):
        cells = row.find_all("td")
        if len(cells) < 12:
            continue
        entries.append({
            "finish_position": _int(cells[0].get_text()),
            "frame_number": _int(cells[1].get_text()),
            "horse_number": _int(cells[2].get_text()),
            "horse_name": cells[3].get_text(strip=True),
            "popularity": _int(cells[10].get_text()),
            "odds": _float(cells[9].get_text()),
        })
    return {"race_id": race_id, "entries": entries}


async def fetch_horse_profile(horse_id: str) -> dict:
    """馬プロフィール（名前・性別・生年）を取得する"""
    url = f"{NETKEIBA_BASE}/horse/{horse_id}/"
    async with RateLimitedClient() as client:
        resp = await client.get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    profile = {"horse_id": horse_id}
    dl = soup.find("dl", class_="db_prof_table")
    if dl:
        for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
            key = dt.get_text(strip=True)
            val = dd.get_text(strip=True)
            if key == "生年月日":
                m = re.search(r"(\d{4})", val)
                if m:
                    profile["birth_year"] = int(m.group(1))
            elif key == "性別":
                profile["sex"] = val
    name_tag = soup.find("h1", class_="horse_title")
    if name_tag:
        profile["name"] = name_tag.get_text(strip=True)
    return profile


def _parse_date(text: str):
    m = re.search(r"(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})", text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _parse_payout(text: str):
    # "1,234,567円" → 1234567
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _int(text: str):
    try:
        return int(re.sub(r"\D", "", text))
    except (ValueError, TypeError):
        return None


def _float(text: str):
    try:
        return float(re.sub(r"[^\d.]", "", text))
    except (ValueError, TypeError):
        return None
