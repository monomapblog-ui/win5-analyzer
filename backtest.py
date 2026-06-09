"""WIN5 バックテスト

4セット打法（各27通り×100円=2700円、計10800円）が
過去データで何回的中し、回収率がどうだったかを検証する。

使い方:
  python backtest.py          # 全期間
  python backtest.py --last 6 # 直近6年
  python backtest.py --year 2024
"""
import argparse
from datetime import date

from sqlalchemy import select, extract
from utils.db import init_db, SessionLocal, Win5Event, Win5Slot


# ─────────────────────────────────────────────
# 4セット定義（buy.py と同じ人気ピック）
# ─────────────────────────────────────────────

SETS = [
    {
        "label": "セットA",
        # slot_idx: [人気リスト]  固定=1個、流し=3個
        "slots": {
            0: [1],
            1: [1, 2, 4],
            2: [2, 3, 5],
            3: [4, 5, 7],
            4: [3],
        },
    },
    {
        "label": "セットB",
        "slots": {
            0: [1],
            1: [2],
            2: [2, 3, 5],
            3: [4, 6, 8],
            4: [3, 4, 6],
        },
    },
    {
        "label": "セットC",
        "slots": {
            0: [1],
            1: [1, 2, 4],
            2: [3],
            3: [4, 6, 7],
            4: [3, 5, 6],
        },
    },
    {
        "label": "セットD",
        "slots": {
            0: [2],
            1: [1, 3, 5],
            2: [2, 4, 6],
            3: [4],
            4: [3, 5, 7],
        },
    },
]

COST_PER_SET  = 2_700   # 27通り × 100円
TOTAL_COST    = COST_PER_SET * len(SETS)  # 10,800円


def set_hits(slot_pops: list[int], s: dict) -> bool:
    """
    5スロットの勝ち馬人気リストと1セット定義を比較し、
    そのセット内に的中組み合わせがあるかを返す。
    （デカルト積全探索不要：各スロット個別チェックで十分）
    """
    for slot_idx, accepted in s["slots"].items():
        winner_pop = slot_pops[slot_idx]
        if winner_pop not in accepted:
            return False
    return True


# ─────────────────────────────────────────────
# バックテスト本体
# ─────────────────────────────────────────────

def run_backtest(years: list[int] | None = None):
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

    _report(rows, years)


def _report(rows: list[dict], years: list[int] | None):
    n_total = len(rows)
    label = "全期間" if not years else f"{min(years)}〜{max(years)}年"

    print(f"\n{'='*65}")
    print(f"  WIN5 バックテスト結果  {label}  ({n_total}開催)")
    print(f"  購入戦略: 4セット × 2,700円 = 10,800円/回")
    print(f"{'='*65}")

    # ─── セット別集計 ───
    set_stats = []
    for s in SETS:
        hit_events = [r for r in rows if set_hits(r["pops"], s)]
        total_invested = n_total * COST_PER_SET
        total_return   = sum(r["payout"] for r in hit_events)
        roi = total_return / total_invested * 100 if total_invested else 0
        set_stats.append({
            "label":          s["label"],
            "hits":           len(hit_events),
            "hit_rate":       len(hit_events) / n_total * 100 if n_total else 0,
            "avg_payout":     int(total_return / len(hit_events)) if hit_events else 0,
            "max_payout":     max((r["payout"] for r in hit_events), default=0),
            "total_invested": total_invested,
            "total_return":   total_return,
            "roi":            roi,
            "hit_events":     hit_events,
        })

    print("\n■ セット別 的中成績")
    print(f"  {'セット':>8}  {'的中':>5}  {'的中率':>7}  {'平均払戻':>12}  {'最高払戻':>14}  {'回収率':>7}")
    print(f"  {'-'*65}")
    for st in set_stats:
        print(
            f"  {st['label']:>8}  "
            f"{st['hits']:>4}回  "
            f"{st['hit_rate']:>6.2f}%  "
            f"{st['avg_payout']:>12,}円  "
            f"{st['max_payout']:>14,}円  "
            f"{st['roi']:>6.1f}%"
        )

    # ─── 合算（4セットいずれか的中） ───
    any_hit = [r for r in rows if any(set_hits(r["pops"], s) for s in SETS)]
    all_invested = n_total * TOTAL_COST
    all_return   = sum(r["payout"] for r in any_hit)
    all_roi      = all_return / all_invested * 100 if all_invested else 0

    print(f"\n■ 4セット合算（いずれか1セット以上的中）")
    print(f"  的中回数  : {len(any_hit):,}回 / {n_total:,}開催")
    print(f"  的中率    : {len(any_hit)/n_total*100:.2f}%  （約{n_total//max(len(any_hit),1)}回に1回）")
    print(f"  総投資額  : {all_invested:,}円")
    print(f"  総払戻額  : {all_return:,}円")
    print(f"  回収率    : {all_roi:.1f}%")
    print(f"  平均払戻  : {int(all_return/len(any_hit)):,}円" if any_hit else "  平均払戻  : -")
    print(f"  最高払戻  : {max(r['payout'] for r in any_hit):,}円" if any_hit else "  最高払戻  : -")

    # ─── ゾーン別 的中率 ───
    print("\n■ ゾーン別 的中率（4セット合算）")
    for zone in ["low", "target", "high"]:
        zone_rows = [r for r in rows if r["zone"] == zone]
        zone_hits = [r for r in zone_rows if any(set_hits(r["pops"], s) for s in SETS)]
        if not zone_rows:
            continue
        rate = len(zone_hits) / len(zone_rows) * 100
        avg_pay = int(sum(r["payout"] for r in zone_hits) / len(zone_hits)) if zone_hits else 0
        zone_label = {"low": "低(≤14)", "target": "ターゲット(15-22)", "high": "高(≥23)"}[zone]
        print(f"  {zone_label:>20}: {len(zone_rows):>4}開催  的中{len(zone_hits):>3}回({rate:>5.1f}%)  平均払戻{avg_pay:>12,}円")

    # ─── 年別推移 ───
    print("\n■ 年別 的中率・回収率")
    print(f"  {'年':>6}  {'開催':>5}  {'的中':>5}  {'的中率':>7}  {'回収率':>8}")
    print(f"  {'-'*42}")
    year_map: dict[int, list] = {}
    for r in rows:
        y = r["held_date"].year
        year_map.setdefault(y, []).append(r)
    for y in sorted(year_map):
        yr = year_map[y]
        yh = [r for r in yr if any(set_hits(r["pops"], s) for s in SETS)]
        invested = len(yr) * TOTAL_COST
        returned = sum(r["payout"] for r in yh)
        roi = returned / invested * 100
        print(f"  {y:>6}年  {len(yr):>4}回  {len(yh):>4}回  {len(yh)/len(yr)*100:>6.1f}%  {roi:>7.1f}%")

    # ─── 的中払戻TOP10 ───
    top_hits = sorted(any_hit, key=lambda r: -r["payout"])[:10]
    if top_hits:
        print("\n■ 的中払戻 TOP10")
        print(f"  {'日付':>12}  {'人気パターン':>20}  {'和':>4}  {'払戻':>14}")
        for r in top_hits:
            print(
                f"  {str(r['held_date']):>12}  "
                f"{str(r['pops']):>20}  "
                f"{r['popularity_sum']:>4}  "
                f"{r['payout']:>14,}円"
            )

    # ─── 購入金額の適正分析 ───
    _analyze_optimal_stake(rows, any_hit, n_total)


def _analyze_optimal_stake(rows, any_hit, n_total):
    """的中率・払戻から適正購入金額を試算"""
    hit_rate   = len(any_hit) / n_total if n_total > 0 else 0
    avg_payout = int(sum(r["payout"] for r in any_hit) / len(any_hit)) if any_hit else 0

    # 破産しないための最低資金（的中まで平均何回かかるか）
    avg_rounds_to_hit = int(1 / hit_rate) if hit_rate else 9999
    min_bankroll = avg_rounds_to_hit * TOTAL_COST

    # 期待値（1回10800円投資した場合）
    ev = hit_rate * avg_payout - TOTAL_COST

    print(f"\n■ 購入金額の適正分析")
    print(f"  的中率          : {hit_rate*100:.2f}%  （平均{avg_rounds_to_hit}回に1回）")
    print(f"  的中時平均払戻  : {avg_payout:,}円")
    print(f"  1回あたり期待値 : {ev:+,.0f}円  （投資10,800円に対して）")
    print(f"  期待値率        : {(hit_rate*avg_payout/TOTAL_COST)*100:.1f}%")
    print()
    print(f"  【破産しない目安資金】")
    print(f"  的中まで平均{avg_rounds_to_hit}回 × 10,800円 = {min_bankroll:,}円")
    print()
    print(f"  【資金別 推奨購入スタンス】")
    for bankroll in [50_000, 100_000, 300_000, 500_000]:
        max_rounds = bankroll // TOTAL_COST
        survive_prob = (1 - hit_rate) ** max_rounds * 100
        print(
            f"  {bankroll:>8,}円の資金 → {max_rounds:>3}回継続可能  "
            f"全損リスク: {survive_prob:.1f}%"
        )


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="WIN5 バックテスト")
    parser.add_argument("--year", type=int, action="append", dest="years", metavar="YYYY")
    parser.add_argument("--last", type=int, metavar="N")
    parser.add_argument("--all",  action="store_true")
    args = parser.parse_args()

    current_year = date.today().year
    if args.all or (not args.last and not args.years):
        years = None
    elif args.last:
        years = list(range(current_year - args.last + 1, current_year + 1))
    else:
        years = args.years

    run_backtest(years)


if __name__ == "__main__":
    main()
