"""JRA公式サイトからWIN5対象レースのスケジュール・出馬表を収集"""
import re
from datetime import date
from bs4 import BeautifulSoup
from utils.http import RateLimitedClient

JRA_BASE = "https://www.jra.go.jp"
WIN5_SCHEDULE_URL = f"{JRA_BASE}/keiba/overseas/win5/"


async def fetch_win5_schedule() -> list[dict]:
    """WIN5開催スケジュールを取得する（直近・過去含む）"""
    async with RateLimitedClient() as client:
        resp = await client.get(WIN5_SCHEDULE_URL)
    soup = BeautifulSoup(resp.text, "lxml")

    schedules = []
    for row in soup.select("table.win5_schedule tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        date_text = cells[0].get_text(strip=True)
        parsed = _parse_date(date_text)
        if parsed:
            schedules.append({"held_date": parsed, "raw": date_text})
    return schedules


async def fetch_race_card(race_id: str) -> dict:
    """出馬表ページから馬・枠・馬番・人気情報を取得する"""
    url = f"{JRA_BASE}/JRADB/accessF.html?RACE_ID={race_id}&type=b3"
    async with RateLimitedClient() as client:
        resp = await client.get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    entries = []
    for row in soup.select("table.race_table tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        entries.append({
            "frame_number": _int(cells[0].get_text()),
            "horse_number": _int(cells[1].get_text()),
            "horse_name": cells[3].get_text(strip=True),
        })
    return {"race_id": race_id, "entries": entries}


def _parse_date(text: str):
    m = re.search(r"(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})", text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _int(text: str):
    try:
        return int(re.sub(r"\D", "", text))
    except ValueError:
        return None
