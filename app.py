"""WIN5 買い目生成 Web アプリ"""
from flask import Flask, render_template, request, jsonify
import time
import re
from datetime import date

from collectors.netkeiba import _get, fetch_win5_by_date
from collectors.shutuba import fetch_odds
from buy import get_win5_race_ids, generate_pure_zone_sets
from bs4 import BeautifulSoup


def _fetch_race_info(race_id: str) -> dict:
    """出馬表ページから頭数・馬場・距離を取得"""
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    try:
        resp = _get(url)
        soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")

        # 馬場・距離
        course_type = track_condition = distance = None
        race_data = soup.find("div", class_="RaceData01")
        if race_data:
            text = race_data.get_text(" ", strip=True)
            m = re.search(r"(芝|ダート|ダ|障害)([\d,]+)m", text)
            if m:
                raw = m.group(1)
                course_type = "芝" if raw == "芝" else "ダート"
                distance = int(m.group(2).replace(",", ""))
            for cond in ["不良", "重", "稍重", "良"]:
                if cond in text:
                    track_condition = cond
                    break

        # 頭数
        table = soup.find("table", class_=re.compile(r"Shutuba_Table|shutuba"))
        field_size = 0
        if table:
            field_size = len([
                r for r in table.find_all("tr")
                if r.find("td") and re.search(r"^\d+$", (r.find("td").get_text(strip=True) or ""))
            ])

        return {
            "field_size":      field_size,
            "course_type":     course_type,
            "distance":        distance,
            "track_condition": track_condition,
        }
    except Exception as e:
        print(f"[WARN] race_info取得失敗 {race_id}: {e}")
        return {"field_size": 0, "course_type": None, "distance": None, "track_condition": None}

app = Flask(__name__)


def _latest_win5_date() -> str:
    try:
        resp = _get("https://race.netkeiba.com/top/win5.html")
        soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")
        dates = []
        for a in soup.find_all("a", href=True):
            m = re.search(r"win5\.html\?date=(\d{8})", a["href"])
            if m:
                dates.append(m.group(1))
        if dates:
            return sorted(dates)[-1]
    except Exception:
        pass
    return date.today().strftime("%Y%m%d")


def _fetch_slots(date_str: str):
    print(f"[INFO] WIN5レース取得: {date_str}")
    slots_info = get_win5_race_ids(date_str)
    if not slots_info:
        return None, None, f"{date_str} のWIN5データが見つかりません（開催がないか、まだ公開されていない可能性があります）"

    print(f"[INFO] {len(slots_info)}レース取得完了")
    slots_odds = []
    for slot in slots_info:
        race_id = slot.get("race_id")
        if not race_id:
            print(f"[WARN] slot{slot['slot_number']} race_id なし")
            slots_odds.append([])
            continue
        try:
            print(f"[INFO] オッズ取得: {slot['name']} ({race_id})")
            odds = fetch_odds(race_id)
            print(f"[INFO]   → {len(odds)}頭")
            slots_odds.append(odds)
        except Exception as e:
            print(f"[ERROR] オッズ取得失敗: {e}")
            slots_odds.append([])
        time.sleep(0.5)

    empty = [i+1 for i, o in enumerate(slots_odds) if not o]
    if empty:
        print(f"[WARN] オッズ未取得スロット: {empty}")

    return slots_info, slots_odds, None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/check", methods=["POST"])
def check_week():
    """今週の購入判定（買う/スキップ）"""
    data = request.get_json()
    date_str = data.get("date", "").strip()
    if not date_str:
        date_str = _latest_win5_date()

    slots_info = get_win5_race_ids(date_str)
    if not slots_info:
        return jsonify({"error": f"{date_str} のWIN5データが見つかりません"}), 404

    race_details = []
    for slot in slots_info:
        race_id = slot.get("race_id")
        if not race_id:
            race_details.append({"slot": slot["slot_number"], "name": slot["name"],
                                  "field_size": 0, "track_condition": None})
            continue
        info = _fetch_race_info(race_id)
        info["slot"] = slot["slot_number"]
        info["name"] = slot["name"]
        info["race_id"] = race_id
        race_details.append(info)
        time.sleep(0.5)

    field_sizes = [d["field_size"] for d in race_details if d["field_size"] > 0]
    avg_field = sum(field_sizes) / len(field_sizes) if field_sizes else 0
    heavy_count = sum(1 for d in race_details if d["track_condition"] in ("重", "不良"))

    skip_reasons = []
    if avg_field > 0 and avg_field < 12:
        skip_reasons.append(f"平均出走頭数が{avg_field:.1f}頭（12頭未満）→ ターゲット率が低い週")
    if heavy_count >= 3:
        skip_reasons.append(f"重・不良馬場が{heavy_count}レース（3レース以上）→ 荒れやすい週")

    verdict = "SKIP" if skip_reasons else "BUY"

    return jsonify({
        "date": date_str,
        "date_label": f"{date_str[:4]}年{date_str[4:6]}月{date_str[6:]}日",
        "verdict": verdict,
        "avg_field_size": round(avg_field, 1),
        "heavy_count": heavy_count,
        "skip_reasons": skip_reasons,
        "races": race_details,
    })


@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.get_json()
    budget = int(data.get("budget", 50000))
    date_str = data.get("date", "").strip()

    if not date_str:
        date_str = _latest_win5_date()
        print(f"[INFO] 最新WIN5日付: {date_str}")

    if budget < 1000:
        return jsonify({"error": "予算は1,000円以上を指定してください"}), 400

    slots_info, slots_odds, err = _fetch_slots(date_str)
    if err:
        return jsonify({"error": err}), 404

    sets = generate_pure_zone_sets(slots_odds, budget)
    if not sets:
        empty_slots = [i+1 for i, o in enumerate(slots_odds) if not o]
        msg = "買い目を生成できませんでした"
        if empty_slots:
            msg += f"（slot{empty_slots} のオッズ取得失敗）"
        else:
            msg += "（オッズデータが不完全）"
        return jsonify({"error": msg}), 500

    total_combos = sum(s["combos"] for s in sets)
    total_cost = total_combos * 100

    tickets = []
    for i, s in enumerate(sets):
        slot_details = []
        for j, (info, horses) in enumerate(zip(slots_info, s["slot_horses"])):
            nums = sorted([h["horse_number"] for h in horses])
            slot_details.append({
                "slot": j + 1,
                "race_name": info["name"],
                "popularity_range": f"{s['lo'][j]}〜{s['hi'][j]}番人気",
                "horses": [
                    {
                        "number": h["horse_number"],
                        "name": h["horse_name"],
                        "popularity": h["popularity"],
                        "odds": h.get("odds", "-"),
                    }
                    for h in horses
                ],
                "numbers": nums,
            })
        tickets.append({
            "ticket_no": i + 1,
            "combos": s["combos"],
            "cost": s["combos"] * 100,
            "lo": list(s["lo"]),
            "hi": list(s["hi"]),
            "sum_lo": sum(s["lo"]),
            "sum_hi": sum(s["hi"]),
            "slots": slot_details,
        })

    return jsonify({
        "date": date_str,
        "date_label": f"{date_str[:4]}年{date_str[4:6]}月{date_str[6:]}日",
        "budget": budget,
        "total_tickets": len(tickets),
        "total_combos": total_combos,
        "total_cost": total_cost,
        "tickets": tickets,
        "races": [
            {"slot": i + 1, "name": info["name"], "race_id": info.get("race_id")}
            for i, info in enumerate(slots_info)
        ],
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
