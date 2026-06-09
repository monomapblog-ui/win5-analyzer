"""出馬表・オッズ取得

URL:
  出馬表: https://race.netkeiba.com/race/shutuba.html?race_id=RACEID
  単勝オッズ: https://race.netkeiba.com/odds/index.html?race_id=RACEID&type=b1
"""
import re
from collectors.netkeiba import _get
from bs4 import BeautifulSoup


def fetch_shutuba(race_id: str) -> list[dict]:
    """
    出馬表から馬番・馬名を取得する。
    返り値: [{"horse_number": 1, "horse_name": "xxx"}, ...]
    """
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    resp = _get(url)
    soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")

    horses = []
    table = soup.find("table", class_=re.compile(r"Shutuba_Table|shutuba"))
    if table is None:
        table = soup.find("table")
    if table is None:
        return horses

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        horse_number = _parse_int(cells[1].get_text()) if len(cells) > 1 else None
        if horse_number is None:
            continue
        horse_name = cells[3].get_text(strip=True) if len(cells) > 3 else ""
        horses.append({"horse_number": horse_number, "horse_name": horse_name})

    return horses


def fetch_odds(race_id: str) -> list[dict]:
    """
    単勝オッズページから馬番・オッズを取得し人気順に並べる。
    返り値: [{"horse_number": 1, "horse_name": "xxx", "odds": 2.5, "popularity": 1}, ...]
    """
    url = f"https://race.netkeiba.com/odds/index.html?race_id={race_id}&type=b1"
    resp = _get(url)
    soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")

    horses = []

    # 単勝オッズテーブル
    table = soup.find("table", id=re.compile(r"odds_tan_table|OddsTanQuinellaWide"))
    if table is None:
        table = soup.find("table", class_=re.compile(r"Odds.*Table|odds.*table", re.I))
    if table is None:
        for t in soup.find_all("table"):
            rows = t.find_all("tr")
            if len(rows) > 5:
                table = t
                break

    if table:
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            horse_number = _parse_int(cells[0].get_text())
            if horse_number is None:
                continue
            horse_name = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            odds_text = cells[-1].get_text(strip=True) if cells else ""
            odds = _parse_float(odds_text)
            if odds and odds > 0:
                horses.append({
                    "horse_number": horse_number,
                    "horse_name":   horse_name,
                    "odds":         odds,
                })

    # オッズ順にソートして人気を付与
    horses.sort(key=lambda x: x["odds"])
    for i, h in enumerate(horses):
        h["popularity"] = i + 1

    return horses


def _parse_int(text):
    if text is None:
        return None
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else None


def _parse_float(text):
    if text is None:
        return None
    s = re.sub(r"[^\d.]", "", str(text))
    try:
        return float(s) if s else None
    except ValueError:
        return None
