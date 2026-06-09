"""WIN5 買い目最適化

過去データから的中率を最大化する人気の組み合わせをグリッドサーチし、
最適な4セット構成（予算108通り以内）を提案する。

使い方:
  python optimize.py              # 全期間
  python optimize.py --last 6    # 直近6年
  python optimize.py --budget 108 # 予算通り数（デフォルト108）
  python optimize.py --top 20    # 上位20件表示
"""
import argparse
from collections import Counter
from datetime import date
from itertools import combinations

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

def hits(pops: list[int], selection: list[list[int]]) -> bool:
    """5スロット全てが選択範囲内なら的中"""
    return all(pops[i] in selection[i] for i in range(5))


def slot_freq(rows: list[dict], slot_idx: int, max_pop: int = 12) -> list[tuple[int, int]]:
    """スロットの人気別出現頻度（降順）"""
    cnt = Counter(r["pops"][slot_idx] for r in rows)
    return sorted(
        [(p, cnt.get(p, 0)) for p in range(1, max_pop + 1)],
        key=lambda x: -x[1]
    )


def best_pops_for_slot(rows: list[dict], slot_idx: int, k: int, max_pop: int = 12) -> list[int]:
    """スロットの上位k人気を貪欲に選択（出現頻度ベース）"""
    freq = slot_freq(rows, slot_idx, max_pop)
    return sorted([p for p, _ in freq[:k]])


def calc_hit_stats(rows: list[dict], selection: list[list[int]]) -> dict:
    """選択に対する的中統計を計算"""
    hit_rows = [r for r in rows if hits(r["pops"], selection)]
    n = len(rows)
    total_invested = n * _combo_count(selection) * 100
    total_return   = sum(r["payout"] for r in hit_rows)
    roi = total_return / total_invested * 100 if total_invested else 0
    return {
        "selection":      selection,
        "combos":         _combo_count(selection),
        "hits":           len(hit_rows),
        "hit_rate":       len(hit_rows) / n * 100 if n else 0,
        "total_return":   total_return,
        "roi":            roi,
        "avg_payout":     int(total_return / len(hit_rows)) if hit_rows else 0,
        "hit_rows":       hit_rows,
    }


def _combo_count(selection: list[list[int]]) -> int:
    result = 1
    for s in selection:
        result *= len(s)
    return result


# ─────────────────────────────────────────────
# 予算内でのサイズ配分を列挙
# ─────────────────────────────────────────────

def enum_size_configs(budget: int, n_slots: int = 5, min_size: int = 1, max_size: int = 6) -> list[tuple]:
    """
    n_slots個の整数 (s0..sn) で積がbudget以下になる全組み合わせを列挙。
    s0 <= s1 <= ... でソートして重複を除去。
    """
    configs = set()

    def _prod(lst):
        r = 1
        for x in lst:
            r *= x
        return r

    def recurse(slot: int, current: list):
        if slot == n_slots:
            if _prod(current) <= budget:
                configs.add(tuple(sorted(current)))
            return
        for size in range(min_size, max_size + 1):
            if _prod(current + [size]) > budget:
                break
            recurse(slot + 1, current + [size])

    recurse(0, [])
    return sorted(configs)


# ─────────────────────────────────────────────
# 最適化メイン
# ─────────────────────────────────────────────

def optimize(
    rows: list[dict],
    budget: int = 108,
    top_n: int = 20,
    max_pop: int = 12,
    zone_filter: str | None = "target",
) -> list[dict]:
    """
    予算budget通り以内で的中率を最大化する人気の組み合わせをグリッドサーチ。

    zone_filter: "target" | "all" | None  → 対象レースをターゲットゾーンに絞るか
    """
    eval_rows = rows if zone_filter is None else [r for r in rows if r["zone"] == zone_filter]
    if not eval_rows:
        eval_rows = rows

    # サイズ配分を列挙（例: 1×1×3×3×4, 1×2×2×3×3 など）
    size_configs = enum_size_configs(budget)
    print(f"  サイズ配分候補: {len(size_configs)}種類")

    results = []
    seen = set()

    for sizes in size_configs:
        # 各スロットで最頻出k人気を選択（貪欲）
        selection = [best_pops_for_slot(eval_rows, i, sizes[i], max_pop) for i in range(5)]
        key = tuple(tuple(s) for s in selection)
        if key in seen:
            continue
        seen.add(key)

        stats = calc_hit_stats(eval_rows, selection)
        stats["sizes"] = sizes
        results.append(stats)

    # 的中率でソート（同率はROI優先）
    results.sort(key=lambda x: (-x["hits"], -x["roi"]))
    return results[:top_n * 3]  # 後でさらに絞る


# ─────────────────────────────────────────────
# 4セット最適分割
# ─────────────────────────────────────────────

def split_into_sets(selection: list[list[int]], n_sets: int = 4) -> list[dict]:
    """
    1つの大選択を4セットに分割して出力用に整形する。
    各スロットの馬をできるだけ均等に振り分ける。
    """
    sets = []
    for i in range(n_sets):
        s = {"label": f"セット{chr(65+i)}", "slots": {}}
        for slot_idx, pops in enumerate(selection):
            # i番目のセットに割り当てる人気（均等分割）
            chunk_size = max(1, len(pops) // n_sets)
            start = i * chunk_size
            end = start + chunk_size if i < n_sets - 1 else len(pops)
            chunk = pops[start:end] if start < len(pops) else [pops[-1]]
            s["slots"][slot_idx] = chunk
        sets.append(s)
    return sets


# ─────────────────────────────────────────────
# レポート出力
# ─────────────────────────────────────────────

def report(rows: list[dict], results: list[dict], budget: int, top_n: int, years):
    n = len(rows)
    label = "全期間" if not years else f"{min(years)}〜{max(years)}年"
    target_rows = [r for r in rows if r["zone"] == "target"]

    print(f"\n{'='*70}")
    print(f"  WIN5 買い目最適化結果  {label}  ({n}開催)")
    print(f"  予算: {budget}通り以内 / ターゲットゾーン({len(target_rows)}開催)で最適化")
    print(f"{'='*70}")

    # スロット別頻度サマリ
    print("\n■ スロット別 勝ち馬人気 頻度TOP5（ターゲットゾーン）")
    print(f"  {'スロット':>8}  " + "  ".join(f"{'#'+str(i+1):>8}" for i in range(5)))
    print(f"  {'-'*55}")
    for slot_idx in range(5):
        freq = slot_freq(target_rows, slot_idx)[:5]
        row = f"  slot{slot_idx+1:>4}    "
        for p, cnt in freq:
            pct = cnt / len(target_rows) * 100
            row += f"  {p}番({pct:.0f}%)"
        print(row)

    # 最適解 TOP
    print(f"\n■ 最適買い目 TOP{top_n}（的中率順）")
    print(f"  {'#':>3}  {'通り':>5}  {'的中':>5}  {'的中率':>7}  {'平均払戻':>12}  {'回収率':>7}  選択人気")
    print(f"  {'-'*75}")

    shown = 0
    best_result = None
    for r in results:
        if shown >= top_n:
            break
        pops_str = "  ".join(f"s{i+1}:{r['selection'][i]}" for i in range(5))
        print(
            f"  {shown+1:>3}  "
            f"{r['combos']:>4}通  "
            f"{r['hits']:>4}回  "
            f"{r['hit_rate']:>6.2f}%  "
            f"{r['avg_payout']:>12,}円  "
            f"{r['roi']:>6.1f}%  "
            f"{pops_str}"
        )
        if shown == 0:
            best_result = r
        shown += 1

    if best_result is None:
        print("  データなし")
        return

    # ベスト構成の詳細
    print(f"\n■ 最適構成の詳細（1位）")
    sel = best_result["selection"]
    combos = best_result["combos"]
    print(f"  総通り数: {combos}通り × 100円 = {combos*100:,}円/回")
    print(f"  的中率  : {best_result['hit_rate']:.2f}%  （平均{int(100/best_result['hit_rate']) if best_result['hit_rate'] else '∞'}回に1回）")
    print(f"  回収率  : {best_result['roi']:.1f}%")
    print()
    for i, pops in enumerate(sel):
        freq = slot_freq(target_rows, i)
        freq_map = {p: cnt for p, cnt in freq}
        pops_detail = "  ".join(
            f"{p}番人気({freq_map.get(p,0)/len(target_rows)*100:.0f}%)" for p in pops
        )
        print(f"  slot{i+1}: {pops_detail}")

    # 的中時の詳細
    hit_rows = best_result["hit_rows"]
    if hit_rows:
        print(f"\n  【的中例】")
        print(f"  {'日付':>12}  {'人気パターン':>22}  {'和':>4}  {'払戻':>14}")
        for r in sorted(hit_rows, key=lambda x: -x["payout"])[:10]:
            print(
                f"  {str(r['held_date']):>12}  "
                f"{str(r['pops']):>22}  "
                f"{r['popularity_sum']:>4}  "
                f"{r['payout']:>14,}円"
            )

    # 現行セットとの比較
    _compare_with_current(rows, best_result)

    # 4セット分割案
    _show_4set_plan(best_result, target_rows)


def _compare_with_current(rows: list[dict], best: dict):
    """現行セット定義との的中率比較"""
    from backtest import SETS, COST_PER_SET

    current_hits = [r for r in rows if any(
        all(r["pops"][i] in s["slots"][i] for i in range(5))
        for s in SETS
    )]
    current_invested = len(rows) * COST_PER_SET * len(SETS)
    current_return   = sum(r["payout"] for r in current_hits)
    current_roi      = current_return / current_invested * 100 if current_invested else 0

    best_invested = len(rows) * best["combos"] * 100
    best_return   = sum(r["payout"] for r in rows if hits(r["pops"], best["selection"]))
    best_roi      = best_return / best_invested * 100 if best_invested else 0

    print(f"\n■ 現行セット vs 最適化後 比較")
    print(f"  {'':>12}  {'通り数':>6}  {'的中':>5}  {'的中率':>7}  {'回収率':>8}")
    print(f"  {'-'*50}")
    n = len(rows)
    print(
        f"  {'現行4セット':>12}  "
        f"{108:>5}通  "
        f"{len(current_hits):>4}回  "
        f"{len(current_hits)/n*100:>6.2f}%  "
        f"{current_roi:>7.1f}%"
    )
    print(
        f"  {'最適化セット':>12}  "
        f"{best['combos']:>5}通  "
        f"{best['hits']:>4}回  "
        f"{best['hit_rate']:>6.2f}%  "
        f"{best_roi:>7.1f}%"
    )


def _show_4set_plan(best: dict, target_rows: list[dict]):
    """最適構成をベースに4セット分割案を表示"""
    sel = best["selection"]

    print(f"\n■ 最適構成を4セットに分割する案")
    print(f"  （各セットは独立した人気の組み合わせ）")

    # スロットごとに「固定（1頭）」「流し（複数）」を決める
    # 出現頻度が高い人気を固定候補とする
    slot_sizes = [len(s) for s in sel]
    print(f"\n  現在の選択サイズ: {slot_sizes}  → 積={_combo_count(sel)}通り")
    print()

    for i, pops in enumerate(sel):
        size_label = "固定" if len(pops) == 1 else f"{len(pops)}頭流し"
        pop_str = " / ".join(f"{p}番人気" for p in pops)
        print(f"  slot{i+1} [{size_label}]: {pop_str}")

    cost = _combo_count(sel) * 100
    print(f"\n  → 1セット {_combo_count(sel)}通り × 100円 = {cost:,}円")
    print(f"  → 同じ構成を1回買うだけでOK（4分割不要）")
    print()
    print(f"  ※ 通り数が多すぎる場合は --budget で絞り込んでください")


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="WIN5 買い目最適化")
    parser.add_argument("--year",   type=int, action="append", dest="years", metavar="YYYY")
    parser.add_argument("--last",   type=int, metavar="N")
    parser.add_argument("--all",    action="store_true")
    parser.add_argument("--budget", type=int, default=108, help="最大通り数（デフォルト108）")
    parser.add_argument("--top",    type=int, default=20,  help="表示件数（デフォルト20）")
    parser.add_argument("--zone",   type=str, default="target", choices=["target", "all"],
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

    zone_filter = None if args.zone == "all" else args.zone
    print(f"最適化実行中（予算{args.budget}通り、ゾーン={args.zone}）...")
    results = optimize(rows, budget=args.budget, top_n=args.top, zone_filter=zone_filter)

    report(rows, results, args.budget, args.top, years)


if __name__ == "__main__":
    main()
