"""出馬表・オッズ取得

確認済み構造:
  オッズ: class=RaceOdds_HorseList_Table  列: 枠|馬番|印|選択|馬名|オッズ
  出馬表: class=Shutuba_Table             列: 枠|馬番|印|馬名|性齢|斤量|騎手|厩舎
"""
import re
from collectors.netkeiba import _get
from bs4 import BeautifulSoup


def fetch_odds(race_id: str) -> list[dict]:
    """
    単勝オッズを取得し人気順に並べる。
    フォールバック順: netkeiba APIの odds JSON → 出馬表ページ → DB
    """
    # ── 1. netkeibaオッズAPI（JavaScriptで読み込まれる実データ）──
    horses = _fetch_odds_from_api(race_id)

    # ── 2. 出馬表で馬名を補完（APIに馬名が含まれないため）──
    if horses:
        shutuba = _fetch_from_shutuba(race_id)
        name_map = {h["horse_number"]: h["horse_name"] for h in shutuba}
        for h in horses:
            if not h.get("horse_name"):
                h["horse_name"] = name_map.get(h["horse_number"], "")
    else:
        # APIが失敗した場合は出馬表にフォールバック
        horses = _fetch_from_shutuba(race_id)

    # 人気がAPIから取れている場合はそのまま使う
    if any(h.get("popularity") for h in horses):
        horses.sort(key=lambda x: (x.get("popularity") is None, x.get("popularity") or 999))
    else:
        valid_odds = [h for h in horses if h["odds"] is not None]
        if valid_odds:
            horses.sort(key=lambda x: (x["odds"] is None, x["odds"] or 9999))
            for i, h in enumerate(horses):
                h["popularity"] = i + 1
        elif horses:
            horses = _fallback_from_db(race_id, horses)
            if not any(h.get("popularity") for h in horses):
                horses.sort(key=lambda x: x["horse_number"])
                for i, h in enumerate(horses):
                    h["popularity"] = i + 1

    return horses


def _fetch_odds_from_api(race_id: str) -> list[dict]:
    """netkeibaの単勝オッズAPIから取得する。
    レスポンス形式: data.odds["1"]["01"] = ["3.7", "", "1"]
      → [単勝オッズ, "", 人気順位]
    """
    api_url = f"https://race.netkeiba.com/api/api_get_jra_odds.html?race_id={race_id}&type=1&action=update"
    try:
        resp = _get(api_url)
        data = resp.json()
        # 単勝は odds["1"]
        tansho = data.get("data", {}).get("odds", {}).get("1", {})
        if not tansho:
            return []
        horses = []
        for horse_num_str, val in tansho.items():
            horse_number = _parse_int(horse_num_str)
            if horse_number is None:
                continue
            # val = ["オッズ", "", "人気順位"]
            odds       = _parse_float(val[0]) if len(val) > 0 else None
            popularity = _parse_int(val[2])   if len(val) > 2 else None
            horses.append({
                "horse_number": horse_number,
                "horse_name":   "",  # 馬名はAPIに含まれないため出馬表で補完
                "odds":         odds,
                "popularity":   popularity,
            })
        return horses
    except Exception as e:
        print(f"[WARN] オッズAPI取得失敗 {race_id}: {e}")
    return []

    # テーブルが見つからなかった場合 → 出馬表ページで再試行
    if not horses:
        horses = _fetch_from_shutuba(race_id)

    valid_odds = [h for h in horses if h["odds"] is not None]
    if valid_odds:
        # オッズあり → ソートして人気付与
        horses.sort(key=lambda x: (x["odds"] is None, x["odds"] or 9999))
        for i, h in enumerate(horses):
            h["popularity"] = i + 1
    elif horses:
        # オッズなし（---.- = 発売前 or 終了済み）→ DBから取得
        horses = _fallback_from_db(race_id, horses)
        # DBにもない場合は馬番順に仮人気を付与
        if not any(h.get("popularity") for h in horses):
            horses.sort(key=lambda x: x["horse_number"])
            for i, h in enumerate(horses):
                h["popularity"] = i + 1

    return horses


def _fetch_from_shutuba(race_id: str) -> list[dict]:
    """出馬表ページからオッズ付き馬リストを取得するフォールバック"""
    try:
        url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
        resp = _get(url)
        soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")

        horses = []
        # 出馬表テーブル: Shutuba_Table
        table = soup.find("table", class_=re.compile(r"Shutuba_Table|ShutubaTable"))
        if table is None:
            return []

        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            horse_number = _parse_int(cells[1].get_text())
            if horse_number is None:
                continue
            horse_name = cells[3].get_text(strip=True)
            # 単勝オッズは列位置が可変 — 数値らしいセルを探す
            odds = None
            for c in cells[5:]:
                v = _parse_float(c.get_text())
                if v and v > 1.0:
                    odds = v
                    break
            horses.append({
                "horse_number": horse_number,
                "horse_name":   horse_name,
                "odds":         odds,
            })

        if horses:
            horses.sort(key=lambda x: (x["odds"] is None, x["odds"] or 9999))
            for i, h in enumerate(horses):
                h["popularity"] = i + 1
        return horses
    except Exception:
        return []


def _fallback_from_db(race_id: str, horses: list[dict]) -> list[dict]:
    """レース終了済みの場合、DBの結果から人気順を取得する"""
    try:
        from utils.db import SessionLocal
        from utils.db import Entry, Race
        from sqlalchemy import select

        with SessionLocal() as session:
            race = session.scalar(select(Race).where(Race.race_id == race_id))
            if race is None:
                return horses
            entries = session.execute(
                select(Entry)
                .where(Entry.race_id == race.id)
                .where(Entry.popularity.is_not(None))
                .order_by(Entry.popularity)
            ).scalars().all()

            pop_map = {e.horse_number: e.popularity for e in entries}
            odds_map = {e.horse_number: e.odds for e in entries}

            for h in horses:
                h["popularity"] = pop_map.get(h["horse_number"])
                h["odds"]       = odds_map.get(h["horse_number"])

            horses = [h for h in horses if h["popularity"] is not None]
            horses.sort(key=lambda x: x["popularity"])
    except Exception:
        pass

    return horses


def fetch_shutuba(race_id: str) -> list[dict]:
    """
    出馬表から枠番・馬番・馬名を取得する。
    返り値: [{"frame_number": 1, "horse_number": 1, "horse_name": "xxx"}, ...]
    """
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    resp = _get(url)
    soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")

    horses = []
    table = soup.find("table", class_="Shutuba_Table")
    if table is None:
        return horses

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        # 枠(0) | 馬番(1) | 印(2) | 馬名(3) | ...
        frame_number  = _parse_int(cells[0].get_text())
        horse_number  = _parse_int(cells[1].get_text())
        if horse_number is None:
            continue
        horse_name = cells[3].get_text(strip=True)
        horses.append({
            "frame_number": frame_number,
            "horse_number": horse_number,
            "horse_name":   horse_name,
        })

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
        return float(s) if s and s != "." else None
    except ValueError:
        return None
