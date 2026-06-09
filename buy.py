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
# ターゲットゾーン戦略（予算指定時）
# 人気の和15〜22の組み合わせが budget_yen円分になる選択を探す
# ─────────────────────────────────────────────

def _count_target_combos(slot_horses: list[list[dict]]) -> list[tuple]:
    """人気の和が15〜22に入る組み合わせを返す"""
    target = []
    for combo in iterproduct(*slot_horses):
        s = sum(h.get("popularity", 0) for h in combo)
        if 15 <= s <= 22:
            target.append(combo)
    return target


def generate_target_zone_coverage(slots_odds: list[list[dict]], budget_yen: int) -> dict:
    """
    人気の和15〜22の組み合わせがbudget_yen円（±20%）になるよう
    各スロットの選択頭数・人気範囲を調整する。

    戦略:
      - 各スロットで「中間人気帯（2〜6番人気）」を中心に選ぶ
      - ターゲットゾーン組み合わせ数が予算÷100に近くなるよう幅を調整
    """
    target_count = budget_yen // 100
    ranked_all = [
        sorted([h for h in odds if h.get("popularity")], key=lambda h: h["popularity"])
        for odds in slots_odds
    ]

    best = None
    best_diff = float("inf")

    # 各スロットで選ぶ人気の「開始位置」と「幅」を探索
    # start: 何番人気から選び始めるか（1〜4）
    # width: 何頭選ぶか（2〜8）
    from itertools import product as iprod
    starts = [1, 2, 3]
    widths = [2, 3, 4, 5, 6, 7, 8]

    for config in iprod(starts, widths, starts, widths, starts, widths, starts, widths, starts, widths):
        # config = (start0, width0, start1, width1, ..., start4, width4)
        slot_horses = []
        valid = True
        for i in range(5):
            start = config[i * 2]
            width = config[i * 2 + 1]
            horses = ranked_all[i][start - 1: start - 1 + width]
            if len(horses) < 1:
                valid = False
                break
            slot_horses.append(horses)
        if not valid:
            continue

        target_combos = _count_target_combos(slot_horses)
        diff = abs(len(target_combos) - target_count)

        if diff < best_diff:
            best_diff = diff
            best = (slot_horses, target_combos)

        # 十分近ければ早期終了（±5%以内）
        if diff <= target_count * 0.05:
            break

    if best is None:
        # フォールバック：上位3〜4頭
        slot_horses = [ranked_all[i][:3] for i in range(5)]
        target_combos = _count_target_combos(slot_horses)
        best = (slot_horses, target_combos)

    slot_horses, target_combos = best
    all_combos = list(iterproduct(*slot_horses))

    return {
        "label":          f"ターゲットゾーン戦略（予算{budget_yen:,}円）",
        "slot_horses":    slot_horses,
        "all_combos":     all_combos,
        "target_combos":  target_combos,
        "target_cost":    len(target_combos) * 100,
        "total_cost":     len(all_combos) * 100,
        "target_count":   len(target_combos),
        "total_count":    len(all_combos),
    }


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

def print_target_zone(date_str: str, slots_info: list[dict], coverage: dict):
    """予算指定時のターゲットゾーン出力（IPAT入力しやすい形式）"""
    print(f"\n{'='*65}")
    print(f"  WIN5 買い目  {date_str[:4]}年{date_str[4:6]}月{date_str[6:]}日")
    print(f"  【ターゲットゾーン戦略】人気の和15〜22")
    print(f"  ターゲット: {coverage['target_count']:,}通り × 100円 = {coverage['target_cost']:,}円")
    print(f"{'='*65}")

    print(f"\n■ 対象レースと選択馬（IPAT入力用）")
    print(f"  {'スロット':>6}  {'レース名':>14}  {'選択頭数':>6}  馬番一覧")
    print(f"  {'-'*60}")

    all_horse_numbers = []
    for i, (info, horses) in enumerate(zip(slots_info, coverage["slot_horses"])):
        nums = [h["horse_number"] for h in horses]
        all_horse_numbers.append(nums)
        nums_str = " ".join(f"{n:>2}番" for n in sorted(nums))
        pop_str  = " ".join(f"({h['popularity']}人気:{h['horse_name'][:4]})" for h in horses)
        print(f"  slot{i+1}  {info['name']:>14}  {len(horses):>4}頭  {nums_str}")
        print(f"  {'':>6}  {'':>14}  {'':>6}  {pop_str}")

    print(f"\n■ IPATでの入力手順")
    print(f"  1. IPAT → WIN5 を選択")
    print(f"  2. 各レースで以下の馬番にチェック")
    for i, nums in enumerate(all_horse_numbers):
        nums_str = "・".join(str(n) for n in sorted(nums))
        print(f"     レース{i+1}（slot{i+1}）: {nums_str}番")
    print(f"  3. 金額: 100円 × {coverage['total_count']}通り = {coverage['total_cost']:,}円")
    print(f"     ※ 内ターゲットゾーン(15〜22): {coverage['target_count']}通り = {coverage['target_cost']:,}円")
    print(f"  4. 確認して購入")

    print(f"\n■ 人気の和の分布")
    pop_sums = [sum(h.get("popularity", 0) for h in c) for c in coverage["all_combos"]]
    low = sum(1 for s in pop_sums if s <= 14)
    tgt = sum(1 for s in pop_sums if 15 <= s <= 22)
    high = sum(1 for s in pop_sums if s >= 23)
    total = len(pop_sums)
    print(f"  {'低(≤14)':>18}: {low:>4}通り ({low/total*100:.1f}%)  ← 今回は捨て")
    print(f"  {'ターゲット(15-22)':>18}: {tgt:>4}通り ({tgt/total*100:.1f}%)  ← 狙い")
    print(f"  {'高(≥23)':>18}: {high:>4}通り ({high/total*100:.1f}%)")
    print(f"\n  ターゲット費用: {coverage['target_cost']:,}円")
    print(f"  全体費用:       {coverage['total_cost']:,}円\n")


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
        # ── ターゲットゾーン戦略 ──
        if args.budget < 1000:
            print(f"⚠ 予算が少なすぎます（最低1,000円以上推奨）")
            return
        print(f"\n予算: {args.budget:,}円  →  ターゲットゾーン(15-22)で約{args.budget//100}通りを目指して選択中...")
        coverage = generate_target_zone_coverage(slots_odds, args.budget)
        print(f"ターゲット組み合わせ: {coverage['target_count']}通り = {coverage['target_cost']:,}円")
        print_target_zone(date_str, slots_info, coverage)
    else:
        # ── 従来4セット戦略 ──
        sets = generate_sets(slots_odds)
        print_buys(date_str, slots_info, slots_odds, sets)


if __name__ == "__main__":
    main()
