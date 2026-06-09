"""WIN5 買い目最適化

アンカー拡張法：
  1. 過去の的中イベントそれぞれを「アンカー」として出発点にする
  2. そのアンカーを確実にカバーしつつ、予算内で最大カバーに貪欲拡張
  3. 4セットを順番に貪欲セットカバーで構築

使い方:
  python optimize.py              # 全期間
  python optimize.py --last 6    # 直近6年
  python optimize.py --budget 27 # 1セットあたりの最大通り数（デフォルト27）
  python optimize.py --sets 4    # セット数（デフォルト4）
  python optimize.py --zone all  # ゾーン絞り込みなし
"""
import argparse
from collections import Counter
from datetime import date

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
# 高速カバレッジ計算（集合演算）
# ─────────────────────────────────────────────

def build_index(rows: list[dict], max_pop: int = 14):
    """slot→pop→rowインデックスの集合を事前構築"""
    idx = [[set() for _ in range(max_pop + 1)] for _ in range(5)]
    for i, r in enumerate(rows):
        for s, p in enumerate(r["pops"]):
            if 1 <= p <= max_pop:
                idx[s][p].add(i)
    return idx


def fast_coverage(sel: list[list[int]], idx: list) -> set:
    """選択に対してカバーされる行インデックスの集合を返す"""
    result = None
    for s, pops in enumerate(sel):
        slot_match: set = set()
        for p in pops:
            if p < len(idx[s]):
                slot_match |= idx[s][p]
        result = slot_match if result is None else result & slot_match
    return result or set()


def combo_count(sel: list[list[int]]) -> int:
    r = 1
    for s in sel:
        r *= len(s)
    return r


# ─────────────────────────────────────────────
# アンカー拡張法
# ─────────────────────────────────────────────

def expand_from_anchor(
    anchor_pops: list[int],
    rows: list[dict],
    idx: list,
    budget: int,
    freq_order: list[list[int]],
) -> tuple[list[list[int]], set]:
    """
    アンカーイベントの5人気を起点に、予算内で最大カバーを達成する選択を構築。
    各ステップで「最も的中数が増えるスロット拡張」を貪欲に選ぶ。

    freq_order[slot_idx] = そのスロットで頻出順に並んだ人気値リスト
    """
    sel = [[p] for p in anchor_pops]
    covered = fast_coverage(sel, idx)

    while True:
        best_gain = 0
        best_new_sel = None
        best_new_covered = covered

        for slot_idx in range(5):
            current_pops = set(sel[slot_idx])
            slot_budget = budget // combo_count(sel) * len(sel[slot_idx])  # 使えるスロット枠

            for pop in freq_order[slot_idx]:
                if pop in current_pops:
                    continue
                new_sel = [list(s) for s in sel]
                new_sel[slot_idx] = sorted(current_pops | {pop})
                if combo_count(new_sel) > budget:
                    break  # これ以上追加しても予算超過
                new_covered = fast_coverage(new_sel, idx)
                gain = len(new_covered) - len(covered)
                if gain > best_gain or (
                    gain == best_gain and best_new_sel is not None and
                    combo_count(new_sel) < combo_count(best_new_sel)
                ):
                    best_gain = gain
                    best_new_sel = new_sel
                    best_new_covered = new_covered
                # 頻出順なので最初の有効なものだけ試す
                break

        if best_new_sel is None:
            break
        sel = best_new_sel
        covered = best_new_covered

    return sel, covered


def find_best_set(
    rows: list[dict],
    idx: list,
    budget: int,
    label: str,
    freq_order: list[list[int]],
) -> dict:
    """全行をアンカーとして試し、最も的中数の多い選択を返す"""
    best = None

    for anchor in rows:
        sel, covered_idx = expand_from_anchor(
            anchor["pops"], rows, idx, budget, freq_order
        )
        n_hits = len(covered_idx)

        if best is None or n_hits > best["hits"] or (
            n_hits == best["hits"] and combo_count(sel) < best["combos"]
        ):
            hit_rows  = [rows[i] for i in sorted(covered_idx)]
            invested  = len(rows) * combo_count(sel) * 100
            returned  = sum(r["payout"] for r in hit_rows)
            best = {
                "label":      label,
                "selection":  sel,
                "combos":     combo_count(sel),
                "hits":       n_hits,
                "hit_rate":   n_hits / len(rows) * 100 if rows else 0,
                "hit_rows":   hit_rows,
                "avg_payout": int(returned / n_hits) if n_hits else 0,
                "roi":        returned / invested * 100 if invested else 0,
            }

    return best or {
        "label": label, "selection": [[1]]*5, "combos": 1,
        "hits": 0, "hit_rate": 0.0, "hit_rows": [], "avg_payout": 0, "roi": 0.0,
    }


# ─────────────────────────────────────────────
# 貪欲セットカバー
# ─────────────────────────────────────────────

def greedy_cover(
    rows: list[dict],
    n_sets: int = 4,
    budget_per_set: int = 27,
) -> list[dict]:
    """
    アンカー拡張法 + 貪欲セットカバーで n_sets セットを構築。
    各セットは「前セットで取れなかったイベント」に対して最適化。
    """
    idx = build_index(rows)

    # スロット別 頻出順人気リスト（拡張時の探索順に使う）
    freq_order = []
    for s in range(5):
        cnt = Counter(r["pops"][s] for r in rows)
        freq_order.append([p for p, _ in sorted(cnt.items(), key=lambda x: -x[1])])

    sets = []
    remaining = list(rows)
    remaining_idx = build_index(remaining)

    for i in range(n_sets):
        label = f"セット{chr(65+i)}"
        print(f"  {label} 探索中（残り{len(remaining)}開催）...")

        best = find_best_set(remaining, remaining_idx, budget_per_set, label, freq_order)
        sets.append(best)

        hit_keys = {(r["held_date"], tuple(r["pops"])) for r in best["hit_rows"]}
        remaining = [r for r in remaining if (r["held_date"], tuple(r["pops"])) not in hit_keys]
        remaining_idx = build_index(remaining)

    return sets


# ─────────────────────────────────────────────
# レポート
# ─────────────────────────────────────────────

def report(rows: list[dict], sets: list[dict], budget_per_set: int, years):
    n = len(rows)
    label = "全期間" if not years else f"{min(years)}〜{max(years)}年"
    target_rows = [r for r in rows if r["zone"] == "target"]
    total_combos        = sum(s["combos"] for s in sets)
    total_cost_per_round = total_combos * 100

    # 4セット合算の的中（重複除去）
    all_hit_keys = {
        (r["held_date"], tuple(r["pops"]))
        for s in sets for r in s["hit_rows"]
    }
    total_hits   = len(all_hit_keys)
    total_inv    = n * total_cost_per_round
    total_ret    = sum(r["payout"] for r in rows if (r["held_date"], tuple(r["pops"])) in all_hit_keys)
    overall_roi  = total_ret / total_inv * 100 if total_inv else 0

    print(f"\n{'='*70}")
    print(f"  WIN5 買い目最適化結果  {label}  ({n}開催)")
    print(f"  戦略: {len(sets)}セット × 最大{budget_per_set}通り ≒ {total_cost_per_round:,}円/回")
    print(f"{'='*70}")

    # スロット別頻度
    print("\n■ スロット別 勝ち馬人気 頻度TOP6（ターゲットゾーン）")
    print(f"  {'スロット':>8}  " + "  ".join(f"{'#'+str(i+1):>8}" for i in range(6)))
    print(f"  {'-'*65}")
    for si in range(5):
        cnt = Counter(r["pops"][si] for r in target_rows)
        freq = sorted(cnt.items(), key=lambda x: -x[1])[:6]
        row = f"  slot{si+1:>4}    "
        for p, c in freq:
            pct = c / len(target_rows) * 100
            row += f"  {p}番({pct:.0f}%)"
        print(row)

    # セット別結果
    print(f"\n■ 最適化4セット構成（アンカー拡張法 + 貪欲セットカバー）")
    print(f"\n  4セット合計: {total_combos}通り × 100円 = {total_cost_per_round:,}円/回")
    print(f"  総的中回数 : {total_hits}回 / {n}開催  ({total_hits/n*100:.2f}%)")
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
    _compare_with_current(rows, sets, total_hits, total_cost_per_round, n)

    # 年別推移
    _yearly_breakdown(rows, sets, total_cost_per_round)

    # 適正購入金額分析
    _stake_analysis(total_hits, n, total_cost_per_round)


def _compare_with_current(rows, opt_sets, opt_hits, opt_cost_per_round, n):
    try:
        from backtest import SETS as CURRENT_SETS
        current_hits = set()
        for r in rows:
            for s in CURRENT_SETS:
                if all(r["pops"][i] in s["slots"][i] for i in range(5)):
                    current_hits.add((r["held_date"], tuple(r["pops"])))

        current_cost = 108 * 100
        current_inv  = n * current_cost
        current_ret  = sum(r["payout"] for r in rows
                          if (r["held_date"], tuple(r["pops"])) in current_hits)
        current_roi  = current_ret / current_inv * 100 if current_inv else 0

        opt_inv = n * opt_cost_per_round
        opt_ret = sum(r["payout"] for r in rows
                     if (r["held_date"], tuple(r["pops"])) in
                     {(r2["held_date"], tuple(r2["pops"])) for s in opt_sets for r2 in s["hit_rows"]})
        opt_roi = opt_ret / opt_inv * 100 if opt_inv else 0

        print(f"■ 現行セット vs 最適化後 比較（全期間）")
        print(f"  {'':>14}  {'1回コスト':>10}  {'総的中':>6}  {'的中率':>7}  {'回収率':>8}")
        print(f"  {'-'*58}")
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


def _yearly_breakdown(rows, sets, total_cost_per_round):
    all_hit_keys = {
        (r["held_date"], tuple(r["pops"]))
        for s in sets for r in s["hit_rows"]
    }
    print(f"■ 年別 的中率・回収率（最適化後）")
    print(f"  {'年':>6}  {'開催':>5}  {'的中':>5}  {'的中率':>7}  {'回収率':>8}")
    print(f"  {'-'*45}")
    year_map: dict[int, list] = {}
    for r in rows:
        y = r["held_date"].year
        year_map.setdefault(y, []).append(r)
    for y in sorted(year_map):
        yr = year_map[y]
        yh = [r for r in yr if (r["held_date"], tuple(r["pops"])) in all_hit_keys]
        invested = len(yr) * total_cost_per_round
        returned = sum(r["payout"] for r in yh)
        roi = returned / invested * 100 if invested else 0
        print(f"  {y:>6}年  {len(yr):>4}回  {len(yh):>4}回  {len(yh)/len(yr)*100:>6.1f}%  {roi:>7.1f}%")
    print()


def _stake_analysis(n_hits, n_total, cost_per_round):
    hit_rate  = n_hits / n_total if n_total else 0
    avg_rounds = int(1 / hit_rate) if hit_rate else 9999
    min_bankroll = avg_rounds * cost_per_round

    print(f"■ 購入金額の適正分析")
    print(f"  的中率         : {hit_rate*100:.2f}%  （平均{avg_rounds}回に1回）")
    print(f"  1回あたりコスト: {cost_per_round:,}円")
    print(f"  破産しない目安 : {avg_rounds}回 × {cost_per_round:,}円 = {min_bankroll:,}円")
    print()
    print(f"  【資金別 推奨スタンス】")
    for bankroll in [50_000, 100_000, 300_000, 500_000, 1_000_000]:
        max_rounds   = bankroll // cost_per_round
        survive_prob = (1 - hit_rate) ** max_rounds * 100 if hit_rate and max_rounds < 10000 else 100.0
        print(
            f"  {bankroll:>10,}円  →  {max_rounds:>4}回継続可能  "
            f"全損リスク: {survive_prob:.1f}%"
        )
    print()


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="WIN5 買い目最適化（アンカー拡張法）")
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
    print(f"最適化実行中（1セット{args.budget}通り × {args.sets}セット、"
          f"ゾーン={args.zone} {len(zone_rows)}開催）...")
    sets = greedy_cover(zone_rows, n_sets=args.sets, budget_per_set=args.budget)

    report(rows, sets, args.budget, years)


if __name__ == "__main__":
    main()
