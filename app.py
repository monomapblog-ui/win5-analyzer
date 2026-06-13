"""WIN5 買い目生成 Web アプリ"""
from flask import Flask, render_template, request, jsonify
import time
import re
from datetime import date

from collectors.netkeiba import _get, fetch_win5_by_date
from collectors.shutuba import fetch_odds
from buy import get_win5_race_ids, generate_pure_zone_sets
from bs4 import BeautifulSoup

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
        return jsonify({"error": "買い目を生成できませんでした（オッズ取得失敗の可能性）"}), 500

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
