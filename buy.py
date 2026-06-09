"""WIN5 自動買い目生成

データドリブン戦略に基づき4セット（各2700円＝計10800円）の買い目を生成する。

戦略サマリ（過去860開催より）:
  - slot1: 大軸（1番人気勝率33%、全スロット最高）→ 1頭固定
  - slot4・slot5: 中穴向き（6〜9番人気が出やすい）
  - ターゲット: 人気の和 15〜22
  - 4セット構成: 各セット 1×3×3×3×1 = 27通り × 100円 = 2700円

使い方:
  python buy.py                    # 直近のWIN5（今週）
  python buy.py --date 20260607    # 日付指定
"""
import argparse
import time
from itertools import product
from collectors.netkeiba import _get, fetch_win5_by_date
from collectors.shutuba import fetch_odds
from bs4 import BeautifulSoup
import re
from datetime import date, timedelta


# ─────────────────────────────────────────────
# WIN5対象レースの取得
# ─────────────────────────────────────────────

def get_win5_race_ids(date_str: str) -> list[dict]:
    """win5.html?date=YYYYMMDD から5レースのrace_idと名称を取得"""
    url = f"https://race.netkeiba.com/top/win5.html?date={date_str}"
    resp = _get(url)
    soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")

    # データなし確認
    if soup.find("p", string=re.compile(r"win5データはありません")):
        return []

    table = soup.find("table", class_="win5raceresult2")
    if table is None:
        return []

    rows = table.find_all("tr")
    race_row = rows[1] if len(rows) > 1 else None
    if race_row is None:
        return []

    slots = []
    cells = race_row.find_all(["td", "th"])
    for slot_num in range(1, 6):
        cell = cells[slot_num] if len(cells) > slot_num else None
        if cell is None:
            continue
        race_id = None
        a = cell.find("a", href=True)
        if a:
            m = re.search(r"race_id=(\d{12})", a["href"])
            if m:
                race_id = m.group(1)
        name = cell.get_text(strip=True)
        slots.append({"slot_number": slot_num, "race_id": race_id, "name": name})

    return slots


# ─────────────────────────────────────────────
# 4セット買い目生成
# ─────────────────────────────────────────────

def generate_sets(slots_odds: list[list[dict]]) -> list[dict]:
    """
    5スロット分のオッズ情報から4セットの買い目を生成する。

    各セットの構造（27通り = 2700円）:
      固定スロット × 2 (各1頭): 大軸 + サブ固定
      流しスロット × 3 (各3頭): 中穴を含む

    セット設計:
      A: slot1固定(1番), slot5固定(3番), slot2/3/4で3頭流し
      B: slot1固定(1番), slot2固定(2番), slot3/4/5で3頭流し
      C: slot1固定(1番), slot3固定(2番), slot2/4/5で3頭流し
      D: slot1固定(2番), slot4固定(4番), slot2/3/5で3頭流し
    """
    sets = []

    # 各スロットの人気別馬番マップを作成
    pop_map = []  # pop_map[slot_idx][popularity] = {"horse_number": N, "horse_name": "xxx", "odds": X}
    for horses in slots_odds:
        m = {h["popularity"]: h for h in horses if h.get("popularity")}
        pop_map.append(m)

    def pick(slot_idx: int, popularities: list[int]) -> list[dict]:
        """指定スロットで指定人気の馬を取得（存在しない場合は近い人気で補完）"""
        result = []
        available = pop_map[slot_idx]
        max_pop = max(available.keys()) if available else 1
        for p in popularities:
            actual_p = p if p in available else min(available.keys(), key=lambda x: abs(x - p))
            horse = available.get(actual_p)
            if horse and horse not in result:
                result.append(horse)
        return result

    # ────────────────────────────
    # セットA: slot1固定(1番), slot5固定(3番), slot2/3/4で3頭流し
    # 人気の和ターゲット: 1 + (2+3+4) + (2+3+4) + (4+5+6) + 3 = 10〜19
    # ────────────────────────────
    set_a = _build_set(
        label="セットA",
        fixed={0: pick(0, [1]), 4: pick(4, [3])},
        fluid={1: pick(1, [1, 2, 4]),
               2: pick(2, [2, 3, 5]),
               3: pick(3, [4, 5, 7])},
        pop_map=pop_map,
    )
    sets.append(set_a)

    # ────────────────────────────
    # セットB: slot1固定(1番), slot2固定(2番), slot3/4/5で3頭流し
    # 人気の和ターゲット: 1 + 2 + (2+3+5) + (4+6+8) + (3+4+6)
    # ────────────────────────────
    set_b = _build_set(
        label="セットB",
        fixed={0: pick(0, [1]), 1: pick(1, [2])},
        fluid={2: pick(2, [2, 3, 5]),
               3: pick(3, [4, 6, 8]),
               4: pick(4, [3, 4, 6])},
        pop_map=pop_map,
    )
    sets.append(set_b)

    # ────────────────────────────
    # セットC: slot1固定(1番), slot3固定(3番), slot2/4/5で3頭流し
    # 人気の和ターゲット: 1 + (1+2+4) + 3 + (4+6+7) + (3+5+6)
    # ────────────────────────────
    set_c = _build_set(
        label="セットC",
        fixed={0: pick(0, [1]), 2: pick(2, [3])},
        fluid={1: pick(1, [1, 2, 4]),
               3: pick(3, [4, 6, 7]),
               4: pick(4, [3, 5, 6])},
        pop_map=pop_map,
    )
    sets.append(set_c)

    # ────────────────────────────
    # セットD: slot1固定(2番), slot4固定(4番), slot2/3/5で3頭流し
    # 1番人気を外した高配当狙い
    # 人気の和ターゲット: 2 + (1+3+5) + (2+4+6) + 4 + (3+5+7)
    # ────────────────────────────
    set_d = _build_set(
        label="セットD",
        fixed={0: pick(0, [2]), 3: pick(3, [4])},
        fluid={1: pick(1, [1, 3, 5]),
               2: pick(2, [2, 4, 6]),
               4: pick(4, [3, 5, 7])},
        pop_map=pop_map,
    )
    sets.append(set_d)

    return sets


def _build_set(label: str, fixed: dict, fluid: dict, pop_map: list) -> dict:
    """セットを構築し、組み合わせと人気の和の範囲を計算する"""
    # 5スロット分の馬リストを構築
    slot_horses = [[] for _ in range(5)]
    for idx, horses in fixed.items():
        slot_horses[idx] = horses[:1]  # 固定は1頭
    for idx, horses in fluid.items():
        slot_horses[idx] = horses[:3]  # 流しは最大3頭

    # 空スロットを補完（念のため）
    for i in range(5):
        if not slot_horses[i] and pop_map[i]:
            slot_horses[i] = [list(pop_map[i].values())[0]]

    # 全組み合わせを生成
    combos = list(product(*slot_horses))

    # 人気の和を計算
    pop_sums = []
    for combo in combos:
        s = sum(h.get("popularity", 0) for h in combo)
        pop_sums.append(s)

    target_combos = [(c, s) for c, s in zip(combos, pop_sums) if 15 <= s <= 22]
    total_cost = len(combos) * 100

    return {
        "label":          label,
        "slot_horses":    slot_horses,
        "combos":         combos,
        "pop_sums":       pop_sums,
        "target_combos":  target_combos,
        "total_cost":     total_cost,
        "target_count":   len(target_combos),
        "target_cost":    len(target_combos) * 100,
    }


# ─────────────────────────────────────────────
# 出力
# ─────────────────────────────────────────────

def print_buys(date_str: str, slots_info: list[dict], slots_odds: list[list[dict]], sets: list[dict]):
    print(f"\n{'='*65}")
    print(f"  WIN5 自動買い目  {date_str[:4]}年{date_str[4:6]}月{date_str[6:]}日")
    print(f"{'='*65}")

    # 対象レース一覧
    print("\n■ 対象レース")
    for i, (info, odds) in enumerate(zip(slots_info, slots_odds)):
        top5 = odds[:6]
        odds_str = "  ".join(f"{h['popularity']}:{h['horse_name']}({h['odds']})" for h in top5)
        print(f"  slot{i+1}: {info['name']}")
        print(f"         {odds_str}")

    # セット別買い目
    total_cost = sum(s["total_cost"] for s in sets)
    print(f"\n■ 買い目（4セット合計 {total_cost:,}円）")

    for s in sets:
        print(f"\n  【{s['label']}】 {s['total_cost']:,}円 ({len(s['combos'])}通り)")
        print(f"  人気の和15〜22に該当: {s['target_count']}通り")

        for i, horses in enumerate(s["slot_horses"]):
            names = " / ".join(f"{h['horse_number']}番{h['horse_name']}(人気{h['popularity']})" for h in horses)
            fixed = "固定" if len(horses) == 1 else "流し"
            print(f"    slot{i+1}[{fixed}]: {names}")

    # ターゲットゾーン組み合わせ一覧
    print(f"\n■ ターゲットゾーン（人気の和15〜22）の組み合わせ詳細")
    for s in sets:
        if s["target_combos"]:
            print(f"\n  【{s['label']}】")
            for combo, pop_sum in sorted(s["target_combos"], key=lambda x: x[1]):
                horses_str = " - ".join(f"{h['horse_number']}番{h['horse_name']}" for h in combo)
                print(f"    和={pop_sum:2d}: {horses_str}")

    print(f"\n  合計購入金額: {total_cost:,}円")
    print()


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="WIN5 自動買い目生成")
    parser.add_argument("--date", type=str, metavar="YYYYMMDD",
                        help="対象日付（省略時は直近WIN5）")
    args = parser.parse_args()

    if args.date:
        date_str = args.date
    else:
        # win5_results.htmlから直近日付を取得
        url = "https://race.netkeiba.com/top/win5_results.html"
        resp = _get(url)
        soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")
        dates = []
        for a in soup.find_all("a", href=True):
            m = re.search(r"win5\.html\?date=(\d{8})", a["href"])
            if m:
                dates.append(m.group(1))
        # win5.htmlのナビリンクも確認
        resp2 = _get("https://race.netkeiba.com/top/win5.html")
        soup2 = BeautifulSoup(resp2.content, "lxml", from_encoding="euc-jp")
        for a in soup2.find_all("a", href=True):
            m = re.search(r"win5\.html\?(?:date=)(\d{8})", a["href"])
            if m and m.group(1) not in dates:
                dates.append(m.group(1))
        date_str = sorted(dates)[-1] if dates else date.today().strftime("%Y%m%d")

    print(f"対象日: {date_str}")

    # 対象レース取得
    slots_info = get_win5_race_ids(date_str)
    if not slots_info:
        print(f"{date_str} のWIN5データが見つかりません。")
        print("使い方: python buy.py --date YYYYMMDD")
        return

    print(f"対象レース: {len(slots_info)}件 取得完了")

    # 各レースのオッズ取得
    slots_odds = []
    for slot in slots_info:
        race_id = slot.get("race_id")
        if not race_id:
            slots_odds.append([])
            continue
        print(f"  オッズ取得中: {slot['name']} ({race_id})")
        try:
            odds = fetch_odds(race_id)
            slots_odds.append(odds)
        except Exception as e:
            print(f"  ⚠ オッズ取得失敗: {e}")
            slots_odds.append([])
        time.sleep(1)

    # 取得確認
    for i, (info, odds) in enumerate(zip(slots_info, slots_odds)):
        if not odds:
            print(f"  ⚠ slot{i+1} のオッズが取得できませんでした")

    # 買い目生成
    sets = generate_sets(slots_odds)

    # 出力
    print_buys(date_str, slots_info, slots_odds, sets)


if __name__ == "__main__":
    main()
