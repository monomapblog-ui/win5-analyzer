"""WIN5 自動買い目生成

使い方:
  python buy.py                        # 直近のWIN5・従来4セット（10,800円）
  python buy.py --date 20260607        # 日付指定
  python buy.py --budget 50000         # 予算5万円で広範囲カバー
  python buy.py --budget 80000         # 予算8万円で広範囲カバー
  python buy.py --budget 50000 --date 20260607

予算指定時の戦略:
  各スロットで上位k人気を均等カバー（過学習しない広範囲戦略）
  例: 5万円 → 約500通り → 各スロット3〜4頭流し
"""
import argparse
import time
from itertools import product as iterproduct
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
# 純粋ターゲットゾーン戦略（低ゾーン0通り保証）
#
# 原理: 各スロットで [lo, hi] の連続人気帯を選ぶとき
#   sum(lo) >= 15 かつ sum(hi) <= 22 なら
#   全ての組み合わせが必ず和 15〜22 に収まる
# ─────────────────────────────────────────────

def _build_pure_set(lo: tuple, ranked: list, max_avail: list) -> dict | None:
    """
    lo: 各スロットの開始人気（1-indexed）
    sum(lo) >= 15 を前提に hi を最大化して1セットを作る。
    sum(hi) <= 22 制約のもとで最大コンボ数を目指す。
    """
    hi = list(lo)
    budget_rem = 22 - sum(hi)

    # sum(hi) <= 22 の範囲で各スロットに1ずつ追加（幅の小さいスロット優先）
    for _ in range(budget_rem):
        best_s = None
        best_width = 9999
        for s in range(5):
            if hi[s] < max_avail[s]:
                w = hi[s] - lo[s]
                if w < best_width:
                    best_width = w
                    best_s = s
        if best_s is None:
            break
        hi[best_s] += 1

    combos = 1
    for s in range(5):
        combos *= hi[s] - lo[s] + 1

    slot_horses = [ranked[s][lo[s] - 1: hi[s]] for s in range(5)]
    if any(len(h) == 0 for h in slot_horses):
        return None

    return {
        "lo":          tuple(lo),
        "hi":          tuple(hi),
        "combos":      combos,
        "slot_horses": slot_horses,
    }


def generate_pure_zone_sets(slots_odds: list[list[dict]], budget_yen: int, max_tickets: int = 10) -> list[dict]:
    """
    低ゾーン0通り保証の純粋ターゲットゾーンセットを複数生成する。
    各セットは独立したIPATチケットとして入力する。
    IPAT上限に合わせてmax_tickets=10で制限。
    """
    target = budget_yen // 100
    ranked = [
        sorted([h for h in o if h.get("popularity")], key=lambda h: h["popularity"])
        for o in slots_odds
    ]
    max_avail = [len(r) for r in ranked]

    # lo の全候補を列挙（sum(lo) ∈ [15,18], lo_i ∈ [1..6]）
    from itertools import product as iprod
    candidates = []
    for lo in iprod(*[range(1, 7) for _ in range(5)]):
        s = sum(lo)
        if s < 15 or s > 18:
            continue
        if any(lo[i] > max_avail[i] for i in range(5)):
            continue
        ps = _build_pure_set(lo, ranked, max_avail)
        if ps:
            candidates.append(ps)

    # コンボ数が多い順にソートし、重複(同一hi)を除外
    seen_hi = set()
    unique = []
    for c in sorted(candidates, key=lambda x: -x["combos"]):
        if c["hi"] not in seen_hi:
            seen_hi.add(c["hi"])
            unique.append(c)

    # 予算 or 10チケット上限に達するまで貪欲に追加
    selected = []
    total = 0
    for c in unique:
        if total >= target or len(selected) >= max_tickets:
            break
        selected.append(c)
        total += c["combos"]

    return selected


# ─────────────────────────────────────────────
# 従来4セット生成（予算未指定時）
# ─────────────────────────────────────────────

def generate_sets(slots_odds: list[list[dict]]) -> list[dict]:
    pop_map = []
    for horses in slots_odds:
        m = {h["popularity"]: h for h in horses if h.get("popularity")}
        pop_map.append(m)

    def pick(slot_idx: int, popularities: list[int]) -> list[dict]:
        result = []
        available = pop_map[slot_idx]
        if not available:
            return result
        for p in popularities:
            actual_p = p if p in available else min(available.keys(), key=lambda x: abs(x - p))
            horse = available.get(actual_p)
            if horse and horse not in result:
                result.append(horse)
        return result

    sets = []
    configs = [
        ("セットA", {0: [1], 4: [3]},       {1: [1,2,4], 2: [2,3,5], 3: [4,5,7]}),
        ("セットB", {0: [1], 1: [2]},        {2: [2,3,5], 3: [4,6,8], 4: [3,4,6]}),
        ("セットC", {0: [1], 2: [3]},        {1: [1,2,4], 3: [4,6,7], 4: [3,5,6]}),
        ("セットD", {0: [2], 3: [4]},        {1: [1,3,5], 2: [2,4,6], 4: [3,5,7]}),
    ]
    for label, fixed_cfg, fluid_cfg in configs:
        slot_horses = [[] for _ in range(5)]
        for idx, pops in fixed_cfg.items():
            slot_horses[idx] = pick(idx, pops)[:1]
        for idx, pops in fluid_cfg.items():
            slot_horses[idx] = pick(idx, pops)[:3]
        for i in range(5):
            if not slot_horses[i] and pop_map[i]:
                slot_horses[i] = [list(pop_map[i].values())[0]]
        combos = list(iterproduct(*slot_horses))
        pop_sums = [sum(h.get("popularity", 0) for h in c) for c in combos]
        target_combos = [(c, s) for c, s in zip(combos, pop_sums) if 15 <= s <= 22]
        sets.append({
            "label":         label,
            "slot_horses":   slot_horses,
            "combos":        combos,
            "pop_sums":      pop_sums,
            "target_combos": target_combos,
            "total_cost":    len(combos) * 100,
            "target_count":  len(target_combos),
            "target_cost":   len(target_combos) * 100,
        })
    return sets


# ─────────────────────────────────────────────
# 出力
# ─────────────────────────────────────────────

def print_pure_sets(date_str: str, slots_info: list[dict], sets: list[dict], budget_yen: int):
    """純粋ターゲットゾーンセットの出力（全組み合わせが和15〜22）"""
    total_combos = sum(s["combos"] for s in sets)
    total_cost   = total_combos * 100

    print(f"\n{'='*65}")
    print(f"  WIN5 買い目  {date_str[:4]}年{date_str[4:6]}月{date_str[6:]}日")
    print(f"  【純粋ターゲットゾーン】全組み合わせが和15〜22（低ゾーン0通り）")
    print(f"  {len(sets)}チケット × 合計 {total_combos}通り = {total_cost:,}円")
    print(f"{'='*65}")

    for ti, s in enumerate(sets):
        print(f"\n  ── チケット{ti+1} （{s['combos']}通り / {s['combos']*100:,}円）──")
        print(f"  人気帯: " + "  ".join(
            f"slot{i+1}=[{s['lo'][i]}〜{s['hi'][i]}番人気]" for i in range(5)
        ))
        print(f"  最小和={sum(s['lo'])}  最大和={sum(s['hi'])}")
        print()
        print(f"  {'スロット':>6}  {'レース名':>14}  馬番（人気順）")
        print(f"  {'-'*55}")
        horse_nums_per_slot = []
        for i, (info, horses) in enumerate(zip(slots_info, s["slot_horses"])):
            nums = sorted([h["horse_number"] for h in horses])
            horse_nums_per_slot.append(nums)
            nums_str = " ".join(f"{n:>2}番" for n in nums)
            pop_str  = " ".join(f"{h['popularity']}人気:{h['horse_name'][:5]}" for h in horses)
            print(f"  slot{i+1}  {info['name']:>14}  {nums_str}")
            print(f"  {'':>6}  {'':>14}  {pop_str}")

        print(f"\n  IPAT入力:")
        for i, nums in enumerate(horse_nums_per_slot):
            print(f"    レース{i+1}: " + "・".join(str(n) for n in nums) + "番")

    print(f"\n{'='*65}")
    print(f"  合計: {len(sets)}チケット  {total_combos}通り  {total_cost:,}円")
    print(f"  全組み合わせが人気の和15〜22（低ゾーン0通り）")
    print(f"{'='*65}\n")


def print_buys(date_str: str, slots_info: list[dict], slots_odds: list[list[dict]], sets: list[dict]):
    """従来4セット出力"""
    print(f"\n{'='*65}")
    print(f"  WIN5 自動買い目  {date_str[:4]}年{date_str[4:6]}月{date_str[6:]}日")
    print(f"{'='*65}")

    print("\n■ 対象レース")
    for i, (info, odds) in enumerate(zip(slots_info, slots_odds)):
        top5 = odds[:6]
        odds_str = "  ".join(f"{h['popularity']}:{h['horse_name']}({h['odds']})" for h in top5)
        print(f"  slot{i+1}: {info['name']}")
        print(f"         {odds_str}")

    total_cost = sum(s["total_cost"] for s in sets)
    print(f"\n■ 買い目（4セット合計 {total_cost:,}円）")

    for s in sets:
        print(f"\n  【{s['label']}】 {s['total_cost']:,}円 ({len(s['combos'])}通り)")
        print(f"  人気の和15〜22に該当: {s['target_count']}通り")
        for i, horses in enumerate(s["slot_horses"]):
            names = " / ".join(f"{h['horse_number']}番{h['horse_name']}(人気{h['popularity']})" for h in horses)
            fixed = "固定" if len(horses) == 1 else "流し"
            print(f"    slot{i+1}[{fixed}]: {names}")

    print(f"\n■ ターゲットゾーン（人気の和15〜22）の組み合わせ")
    for s in sets:
        if s["target_combos"]:
            print(f"\n  【{s['label']}】")
            for combo, pop_sum in sorted(s["target_combos"], key=lambda x: x[1]):
                horses_str = " - ".join(f"{h['horse_number']}番{h['horse_name']}" for h in combo)
                print(f"    和={pop_sum:2d}: {horses_str}")

    print(f"\n  合計購入金額: {total_cost:,}円\n")


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="WIN5 自動買い目生成")
    parser.add_argument("--date",   type=str, metavar="YYYYMMDD")
    parser.add_argument("--budget", type=int, metavar="YEN",
                        help="購入予算（円）。指定時は広範囲カバー戦略を使用")
    args = parser.parse_args()

    # 対象日付の決定
    if args.date:
        date_str = args.date
    else:
        url = "https://race.netkeiba.com/top/win5_results.html"
        resp = _get(url)
        soup = BeautifulSoup(resp.content, "lxml", from_encoding="euc-jp")
        dates = []
        for a in soup.find_all("a", href=True):
            m = re.search(r"win5\.html\?date=(\d{8})", a["href"])
            if m:
                dates.append(m.group(1))
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
        return

    print(f"対象レース: {len(slots_info)}件 取得完了")

    # オッズ取得
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

    for i, (info, odds) in enumerate(zip(slots_info, slots_odds)):
        if not odds:
            print(f"  ⚠ slot{i+1} のオッズが取得できませんでした")

    if args.budget:
        # ── 純粋ターゲットゾーン戦略（低ゾーン0通り）──
        if args.budget < 1000:
            print(f"⚠ 予算が少なすぎます（最低1,000円以上推奨）")
            return
        print(f"\n予算: {args.budget:,}円  →  全組み合わせが和15〜22になるセットを生成中...")
        sets = generate_pure_zone_sets(slots_odds, args.budget)
        total = sum(s["combos"] for s in sets)
        print(f"生成: {len(sets)}チケット × 合計{total}通り = {total*100:,}円")
        print_pure_sets(date_str, slots_info, sets, args.budget)
    else:
        # ── 従来4セット戦略 ──
        sets = generate_sets(slots_odds)
        print_buys(date_str, slots_info, slots_odds, sets)


if __name__ == "__main__":
    main()
