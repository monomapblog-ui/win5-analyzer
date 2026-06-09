"""WIN5 買い目最適化

貪欲セットカバー法で4セットを順番に探索：
  1. 全期間の的中数を最大化する1セット目を探す
  2. 1セット目で取れなかったイベントに対して2セット目を探す
  3. 以降同様に4セットまで繰り返す

使い方:
  python optimize.py              # 全期間
  python optimize.py --last 6    # 直近6年
  python optimize.py --budget 27 # 1セットあたりの予算通り数（デフォルト27）
  python optimize.py --sets 4    # セット数（デフォルト4）
"""
import argparse
from collections import Counter
from datetime import date
from itertools import permutations

from sqlalchemy import select, extract
from utils.db import init_db, SessionLocal, Win5Event, Win5Slot


# ─────────────────────────────────────────────
# データ読み込み
# ─────────────────────────────────────────────

def load_rows(years: list[int] | None = None) -> list[dict]:
    init_db()
    with SessionLocal() as session:
        q = (
            select(Win5Event)
            .where(Win5Event.popularity_sum.is_not(None))
            .where(Win5Event.payout.is_not(None))
        )
        if years:
            q = q.where(extract("year", Win5Event.held_date).in_(years))
        events = session.execute(q.order_by(Win5Event.held_date)).scalars().all()

        rows = []
        for e in events:
            slots = session.execute(
                select(Win5Slot)
                .where(Win5Slot.event_id == e.id)
                .order_by(Win5Slot.slot_number)
            ).scalars().all()
            pops = [s.winner_popularity for s in slots]
            if len(pops) != 5 or any(p is None for p in pops):
                continue
            rows.append({
                "held_date":      e.held_date,
                "payout":         e.payout,
                "popularity_sum": e.popularity_sum,
                "zone":           e.zone,
                "pops":           pops,
            })
    return rows


# ─────────────────────────────────────────────
# コアロジック
# ─────────────────────────────────────────────

def set_hits(pops: list[int], selection: list[list[int]]) -> bool:
    return all(pops[i] in selection[i] for i in range(5))


def combo_count(selection: list[list[int]]) -> int:
    r = 1
    for s in selection:
        r *= len(s)
    return r


def top_k_pops(rows: list[dict], slot_idx: int, k: int, max_pop: int = 12) -> list[int]:
    """スロットの出現頻度上位k人気を返す"""
    cnt = Counter(r["pops"][slot_idx] for r in rows)
    top = sorted(cnt.items(), key=lambda x: -x[1])
    return sorted([p for p, _ in top[:k] if p <= max_pop])


def slot_freq_table(rows: list[dict], max_pop: int = 12) -> list[list[tuple]]:
    """各スロットの人気別出現頻度テーブル"""
    result = []
    for i in range(5):
        cnt = Counter(r["pops"][i] for r in rows)
        freq = sorted([(p, cnt.get(p, 0)) for p in range(1, max_pop + 1)], key=lambda x: -x[1])
        result.append(freq)
    return result


# ─────────────────────────────────────────────
# サイズ配分の列挙（1セット分）
# ─────────────────────────────────────────────

def enum_size_configs(budget: int, n_slots: int = 5, max_size: int = 7) -> list[tuple]:
    """積がbudget以下になるサイズ配分の全パターンを列挙（重複なし・ソート済み）"""
    configs = set()

    def recurse(slot: int, current: list, prod: int):
        if slot == n_slots:
            configs.add(tuple(sorted(current)))
            return
        for size in range(1, max_size + 1):
            new_prod = prod * size
            if new_prod > budget:
                break
            recurse(slot + 1, current + [size], new_prod)

    recurse(0, [], 1)
    return sorted(configs)


# ─────────────────────────────────────────────
# 1セット最適化
# ─────────────────────────────────────────────

def find_best_set(rows: list[dict], budget: int, label: str = "") -> dict:
    """
    残りrowsに対して的中数を最大化する1セットを探す。
    全サイズ配分 × 全スロット順列で探索し、各スロットは貪欲上位k選択。
    """
    if not rows:
        return _empty_set(label)

    size_configs = enum_size_configs(budget)
    best = None

    for sizes in size_configs:
        # スロットへのサイズ割り当ての全順列を試す
        seen_perms = set()
        for perm in permutations(sizes):
            if perm in seen_perms:
                continue
            seen_perms.add(perm)

            selection = [top_k_pops(rows, i, perm[i]) for i in range(5)]
            n_hits = sum(1 for r in rows if set_hits(r["pops"], selection))

            if best is None or n_hits > best["hits"] or (
                n_hits == best["hits"] and combo_count(selection) < best["combos"]
            ):
                hit_rows = [r for r in rows if set_hits(r["pops"], selection)]
                invested  = len(rows) * combo_count(selection) * 100
                returned  = sum(r["payout"] for r in hit_rows)
                best = {
                    "label":      label,
                    "selection":  selection,
                    "sizes":      list(perm),
                    "combos":     combo_count(selection),
                    "hits":       n_hits,
                    "hit_rate":   n_hits / len(rows) * 100,
                    "hit_rows":   hit_rows,
                    "avg_payout": int(returned / n_hits) if n_hits else 0,
                    "roi":        returned / invested * 100 if invested else 0,
                }

    return best or _empty_set(label)


def _empty_set(label: str) -> dict:
    return {
        "label": label, "selection": [[1]]*5, "sizes": [1]*5,
        "combos": 1, "hits": 0, "hit_rate": 0.0,
        "hit_rows": [], "avg_payout": 0, "roi": 0.0,
    }


# ─────────────────────────────────────────────
# 貪欲セットカバー（4セット）
# ─────────────────────────────────────────────

def greedy_cover(rows: list[dict], n_sets: int = 4, budget_per_set: int = 27) -> list[dict]:
    """
    貪欲セットカバー法で n_sets セットを順番に最適化する。
    各セットは「前のセットで取れなかったイベント」を優先的にカバーする。
    """
    sets = []
    remaining = list(rows)

    for i in range(n_sets):
        label = f"セット{chr(65+i)}"
        print(f"  {label} 探索中（残り{len(remaining)}開催）...")
        best = find_best_set(remaining, budget_per_set, label)
        sets.append(best)

        # 的中済みを除外
        hit_keys = {(r["held_date"], tuple(r["pops"])) for r in best["hit_rows"]}
        remaining = [r for r in remaining if (r["held_date"], tuple(r["pops"])) not in hit_keys]

    return sets


# ─────────────────────────────────────────────
# レポート
# ─────────────────────────────────────────────

def report(rows: list[dict], sets: list[dict], budget_per_set: int, years):
    n = len(rows)
    label = "全期間" if not years else f"{min(years)}〜{max(years)}年"
    target_rows = [r for r in rows if r["zone"] == "target"]
    total_cost_per_round = sum(s["combos"] for s in sets) * 100

    print(f"\n{'='*70}")
    print(f"  WIN5 買い目最適化結果  {label}  ({n}開催)")
    print(f"  戦略: {len(sets)}セット × 最大{budget_per_set}通り = 最大{budget_per_set*len(sets)}通り/回")
    print(f"{'='*70}")

    # スロット別頻度
    print("\n■ スロット別 勝ち馬人気 頻度TOP6（ターゲットゾーン）")
    freq_table = slot_freq_table(target_rows)
    print(f"  {'スロット':>8}  " + "  ".join(f"{'#'+str(i+1):>9}" for i in range(6)))
    print(f"  {'-'*65}")
    for slot_idx, freq in enumerate(freq_table):
        row = f"  slot{slot_idx+1:>4}    "
        for p, cnt in freq[:6]:
            pct = cnt / len(target_rows) * 100
            row += f"  {p}番({pct:.0f}%)"
        print(row)

    # 各セット結果
    print(f"\n■ 最適化4セット構成（貪欲セットカバー法）")
    all_hit_keys = set()
    for s in sets:
        for r in s["hit_rows"]:
            all_hit_keys.add((r["held_date"], tuple(r["pops"])))

    total_unique_hits = len(all_hit_keys)
    total_combos      = sum(s["combos"] for s in sets)
    total_invested    = n * total_cost_per_round
    total_returned    = sum(r["payout"] for r in rows
                           if (r["held_date"], tuple(r["pops"])) in all_hit_keys)
    overall_roi       = total_returned / total_invested * 100 if total_invested else 0

    print(f"\n  4セット合計: {total_combos}通り × 100円 = {total_cost_per_round:,}円/回")
    print(f"  総的中回数 : {total_unique_hits}回 / {n}開催  ({total_unique_hits/n*100:.2f}%)")
    print(f"  総回収率   : {overall_roi:.1f}%")
    print()

    for s in sets:
        print(f"  ─── {s['label']} ───")
        print(f"  通り数: {s['combos']:>3}通  的中: {s['hits']:>3}回  "
              f"的中率: {s['hit_rate']:.2f}%  平均払戻: {s['avg_payout']:,}円")
        for i, pops in enumerate(s["selection"]):
            size_label = "固定" if len(pops) == 1 else f"{len(pops)}頭流し"
            pop_str = " / ".join(f"{p}番人気" for p in pops)
            print(f"    slot{i+1} [{size_label:>6}]: {pop_str}")
        if s["hit_rows"]:
            print(f"  的中例:")
            for r in sorted(s["hit_rows"], key=lambda x: -x["payout"])[:3]:
                print(f"    {r['held_date']}  {r['pops']}  {r['payout']:,}円")
        print()

    # 現行との比較
    _compare_with_current(rows, sets, total_unique_hits, total_cost_per_round, n)

    # 年別推移
    _yearly_breakdown(rows, sets)

    # 購入金額の適正分析
    _stake_analysis(rows, total_unique_hits, n, total_cost_per_round)


def _compare_with_current(rows, opt_sets, opt_hits, opt_cost_per_round, n):
    """現行buy.pyのセット定義と比較"""
    try:
        from backtest import SETS as CURRENT_SETS
        current_hits = set()
        for r in rows:
            for s in CURRENT_SETS:
                if all(r["pops"][i] in s["slots"][i] for i in range(5)):
                    current_hits.add((r["held_date"], tuple(r["pops"])))

        current_cost  = 108 * 100
        current_inv   = n * current_cost
        current_ret   = sum(r["payout"] for r in rows
                           if (r["held_date"], tuple(r["pops"])) in current_hits)
        current_roi   = current_ret / current_inv * 100 if current_inv else 0

        opt_inv = n * opt_cost_per_round
        opt_ret = sum(r["payout"] for r in rows
                     if (r["held_date"], tuple(r["pops"])) in
                     {(r2["held_date"], tuple(r2["pops"])) for s in opt_sets for r2 in s["hit_rows"]})
        opt_roi = opt_ret / opt_inv * 100 if opt_inv else 0

        print(f"■ 現行セット vs 最適化後 比較（全期間）")
        print(f"  {'':>14}  {'1回コスト':>10}  {'総的中':>6}  {'的中率':>7}  {'回収率':>8}")
        print(f"  {'-'*55}")
        print(
            f"  {'現行4セット':>14}  {current_cost:>8,}円  "
            f"{len(current_hits):>5}回  "
            f"{len(current_hits)/n*100:>6.2f}%  "
            f"{current_roi:>7.1f}%"
        )
        print(
            f"  {'最適化セット':>14}  {opt_cost_per_round:>8,}円  "
            f"{opt_hits:>5}回  "
            f"{opt_hits/n*100:>6.2f}%  "
            f"{opt_roi:>7.1f}%"
        )
        print()
    except ImportError:
        pass


def _yearly_breakdown(rows: list[dict], sets: list[dict]):
    all_hit_keys = {
        (r["held_date"], tuple(r["pops"]))
        for s in sets for r in s["hit_rows"]
    }
    print(f"■ 年別 的中率・回収率（最適化後）")
    print(f"  {'年':>6}  {'開催':>5}  {'的中':>5}  {'的中率':>7}  {'回収率':>8}")
    print(f"  {'-'*42}")
    year_map: dict[int, list] = {}
    for r in rows:
        y = r["held_date"].year
        year_map.setdefault(y, []).append(r)
    total_cost_per_round = sum(s["combos"] for s in sets) * 100
    for y in sorted(year_map):
        yr = year_map[y]
        yh = [r for r in yr if (r["held_date"], tuple(r["pops"])) in all_hit_keys]
        invested = len(yr) * total_cost_per_round
        returned = sum(r["payout"] for r in yh)
        roi = returned / invested * 100 if invested else 0
        print(f"  {y:>6}年  {len(yr):>4}回  {len(yh):>4}回  {len(yh)/len(yr)*100:>6.1f}%  {roi:>7.1f}%")
    print()


def _stake_analysis(rows, n_hits, n_total, cost_per_round):
    hit_rate = n_hits / n_total if n_total else 0
    all_hit_keys_lookup = set()  # simplified for stake analysis
    avg_rounds = int(1 / hit_rate) if hit_rate else 9999
    min_bankroll = avg_rounds * cost_per_round

    print(f"■ 購入金額の適正分析")
    print(f"  的中率         : {hit_rate*100:.2f}%  （平均{avg_rounds}回に1回）")
    print(f"  1回あたりコスト: {cost_per_round:,}円")
    print(f"  破産しない目安 : {avg_rounds}回 × {cost_per_round:,}円 = {min_bankroll:,}円")
    print()
    print(f"  【資金別 推奨スタンス】")
    for bankroll in [50_000, 100_000, 300_000, 500_000, 1_000_000]:
        max_rounds    = bankroll // cost_per_round
        survive_prob  = (1 - hit_rate) ** max_rounds * 100 if max_rounds < 10000 else 0
        print(
            f"  {bankroll:>10,}円  →  {max_rounds:>4}回継続可能  "
            f"全損リスク: {survive_prob:.1f}%"
        )
    print()


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="WIN5 買い目最適化（貪欲セットカバー法）")
    parser.add_argument("--year",   type=int, action="append", dest="years", metavar="YYYY")
    parser.add_argument("--last",   type=int, metavar="N")
    parser.add_argument("--all",    action="store_true")
    parser.add_argument("--budget", type=int, default=27,
                        help="1セットあたりの最大通り数（デフォルト27）")
    parser.add_argument("--sets",   type=int, default=4,
                        help="セット数（デフォルト4）")
    parser.add_argument("--zone",   type=str, default="target",
                        choices=["target", "all"],
                        help="最適化対象ゾーン（デフォルト: target）")
    args = parser.parse_args()

    current_year = date.today().year
    if args.all or (not args.last and not args.years):
        years = None
    elif args.last:
        years = list(range(current_year - args.last + 1, current_year + 1))
    else:
        years = args.years

    print(f"データ読み込み中...")
    rows = load_rows(years)
    if not rows:
        print("データがありません。collect.py でデータ収集してください。")
        return

    zone_rows = rows if args.zone == "all" else [r for r in rows if r["zone"] == "target"]
    print(f"最適化実行中（1セット{args.budget}通り × {args.sets}セット、ゾーン={args.zone}）...")
    sets = greedy_cover(zone_rows, n_sets=args.sets, budget_per_set=args.budget)

    report(rows, sets, args.budget, years)


if __name__ == "__main__":
    main()
