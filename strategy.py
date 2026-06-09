"""WIN5戦略分析 - データから買い方を導き出す

使い方:
  python strategy.py          # 全期間
  python strategy.py --last 6 # 直近6年
"""
import argparse
from collections import Counter
from datetime import date
from itertools import combinations

from sqlalchemy import select, extract
from utils.db import init_db, SessionLocal, Win5Event, Win5Slot


def load_events(years: list[int] | None = None) -> list[Win5Event]:
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

        # スロットを一緒にロード
        result = []
        for e in events:
            slots = session.execute(
                select(Win5Slot)
                .where(Win5Slot.event_id == e.id)
                .order_by(Win5Slot.slot_number)
            ).scalars().all()
            pops = [s.winner_popularity for s in slots]
            if len(pops) == 5 and all(p is not None for p in pops):
                result.append({
                    "held_date":      e.held_date,
                    "payout":         e.payout,
                    "popularity_sum": e.popularity_sum,
                    "zone":           e.zone,
                    "pops":           pops,  # [slot1, slot2, slot3, slot4, slot5]
                })
        return result


def analyze_strategy(years: list[int] | None = None):
    events = load_events(years)
    target = [e for e in events if e["zone"] == "target"]

    label = f"全期間（{len(events)}開催）" if not years else f"{min(years)}〜{max(years)}年"
    print(f"\n{'='*60}")
    print(f"  WIN5 戦略分析  {label}")
    print(f"  ターゲットゾーン的中: {len(target)}回")
    print(f"{'='*60}")

    # ─────────────────────────────────────────────
    # ① スロット別 勝ち馬人気の分布
    # ─────────────────────────────────────────────
    print("\n■ ① スロット別 勝ち馬人気の分布（ターゲットゾーン）")
    print(f"  {'人気':>4}  " + "  ".join(f"slot{i}" for i in range(1, 6)))
    print(f"  {'-'*45}")

    slot_pop_counts = [{} for _ in range(5)]
    for e in target:
        for i, p in enumerate(e["pops"]):
            slot_pop_counts[i][p] = slot_pop_counts[i].get(p, 0) + 1

    all_pops = sorted({p for e in target for p in e["pops"]})
    for p in all_pops[:12]:
        row = f"  {p:>4}番人気  "
        for i in range(5):
            cnt = slot_pop_counts[i].get(p, 0)
            pct = cnt / len(target) * 100
            row += f" {cnt:3d}({pct:4.1f}%)"
        print(row)

    # ─────────────────────────────────────────────
    # ② 各スロットの「大軸候補」分析
    #    → 1・2番人気が勝つ確率が高いスロット
    # ─────────────────────────────────────────────
    print("\n■ ② スロット別 1〜2番人気の勝率（大軸候補）")
    print(f"  {'スロット':>6}  {'1番人気勝率':>10}  {'2番人気勝率':>10}  {'計':>8}  推奨")
    print(f"  {'-'*50}")

    slot_scores = []
    for i in range(5):
        cnt1 = slot_pop_counts[i].get(1, 0)
        cnt2 = slot_pop_counts[i].get(2, 0)
        pct1 = cnt1 / len(target) * 100
        pct2 = cnt2 / len(target) * 100
        total = pct1 + pct2
        slot_scores.append((i + 1, pct1, pct2, total))

    for slot, p1, p2, total in sorted(slot_scores, key=lambda x: -x[3]):
        mark = "◎ 大軸向き" if total >= 50 else ("○" if total >= 40 else "")
        print(f"  slot{slot}    {p1:8.1f}%  {p2:8.1f}%  {total:6.1f}%  {mark}")

    # ─────────────────────────────────────────────
    # ③ 各スロットの「中穴候補」分析
    #    → 3〜9番人気が勝つ確率
    # ─────────────────────────────────────────────
    print("\n■ ③ スロット別 中穴（3〜9番人気）の勝率")
    print(f"  {'スロット':>6}  {'3-5番人気':>10}  {'6-9番人気':>10}  推奨")
    print(f"  {'-'*45}")

    for i in range(5):
        cnt_35 = sum(slot_pop_counts[i].get(p, 0) for p in range(3, 6))
        cnt_69 = sum(slot_pop_counts[i].get(p, 0) for p in range(6, 10))
        pct_35 = cnt_35 / len(target) * 100
        pct_69 = cnt_69 / len(target) * 100
        mark = "◎ 中穴向き" if pct_35 + pct_69 >= 50 else ("○" if pct_35 + pct_69 >= 40 else "")
        print(f"  slot{i+1}    {pct_35:8.1f}%  {pct_69:8.1f}%  {mark}")

    # ─────────────────────────────────────────────
    # ④ 人気の組み合わせパターン（頻出TOP20）
    # ─────────────────────────────────────────────
    print("\n■ ④ 的中時の人気パターン TOP20（ターゲットゾーン）")
    print(f"  {'パターン':>25}  {'回数':>5}  {'平均払戻':>12}  {'最高払戻':>12}")
    print(f"  {'-'*60}")

    pattern_data: dict[tuple, list[int]] = {}
    for e in target:
        key = tuple(sorted(e["pops"]))
        pattern_data.setdefault(key, []).append(e["payout"])

    sorted_patterns = sorted(pattern_data.items(), key=lambda x: -len(x[1]))
    for pattern, payouts in sorted_patterns[:20]:
        avg = sum(payouts) // len(payouts)
        print(
            f"  {str(list(pattern)):>25}  "
            f"{len(payouts):>5}  "
            f"{avg:>12,}円  "
            f"{max(payouts):>12,}円"
        )

    # ─────────────────────────────────────────────
    # ⑤ 4セット打法 最適構成の提案
    #    人気の和15〜22に収まる組み合わせを
    #    回収率でランキング
    # ─────────────────────────────────────────────
    print("\n■ ⑤ 推奨セット構成（データから導出）")
    _recommend_sets(target)

    # ─────────────────────────────────────────────
    # ⑥ 1番人気を入れるべき位置の分析
    # ─────────────────────────────────────────────
    print("\n■ ⑥ 1番人気を「2ヶ所」入れる場合の最適スロットペア")
    pair_counts: dict[tuple, list[int]] = {}
    for e in target:
        slots_with_pop1 = [i + 1 for i, p in enumerate(e["pops"]) if p == 1]
        if len(slots_with_pop1) >= 2:
            for pair in combinations(sorted(slots_with_pop1), 2):
                pair_counts.setdefault(pair, []).append(e["payout"])
        elif len(slots_with_pop1) == 1:
            pass  # 1ヶ所のみ

    print(f"  {'スロットペア':>12}  {'回数':>5}  {'平均払戻':>12}")
    for pair, payouts in sorted(pair_counts.items(), key=lambda x: -len(x[1]))[:10]:
        avg = sum(payouts) // len(payouts)
        print(f"  slot{pair[0]}×slot{pair[1]}    {len(payouts):>5}  {avg:>12,}円")

    print()


def _recommend_sets(target: list[dict]):
    """頻出パターンから4セット打法の推奨構成を提案"""
    # 各スロットで「よく来る人気」TOP3を抽出
    slot_top = []
    for i in range(5):
        pop_cnt = Counter(e["pops"][i] for e in target)
        top3 = [p for p, _ in pop_cnt.most_common(5) if p <= 9][:3]
        slot_top.append(top3)

    print(f"  各スロットの推奨人気（出現頻度TOP3）:")
    for i, tops in enumerate(slot_top):
        print(f"    slot{i+1}: {tops}番人気")

    # 大軸スロット（1・2番人気勝率最高）
    slot_scores = []
    for i in range(5):
        pop_cnt = Counter(e["pops"][i] for e in target)
        score = pop_cnt.get(1, 0) + pop_cnt.get(2, 0)
        slot_scores.append((i, score))
    axis_slot = max(slot_scores, key=lambda x: x[1])[0]

    print(f"\n  大軸推奨スロット: slot{axis_slot + 1}（1・2番人気勝率最高）")
    print(f"  残り4スロットに中穴を配置")
    print(f"\n  【推奨4セット構成イメージ】")
    print(f"  ※大軸=slot{axis_slot+1}を1頭固定、他スロットで人気の和15〜22に調整")

    # 実際の的中パターンから4セット例を提示
    good = sorted(
        [e for e in target if 16 <= e["popularity_sum"] <= 21],
        key=lambda x: -x["payout"]
    )[:8]
    print(f"\n  参考: 払戻上位8例（和16〜21）")
    print(f"  {'日付':>12}  {'人気パターン':>25}  {'和':>4}  {'払戻':>14}")
    for e in good:
        print(
            f"  {str(e['held_date']):>12}  "
            f"{str(e['pops']):>25}  "
            f"{e['popularity_sum']:>4}  "
            f"{e['payout']:>14,}円"
        )


def main():
    parser = argparse.ArgumentParser(description="WIN5戦略分析")
    parser.add_argument("--year", type=int, action="append", dest="years", metavar="YYYY")
    parser.add_argument("--last", type=int, metavar="N")
    parser.add_argument("--all",  action="store_true")
    args = parser.parse_args()

    current_year = date.today().year
    if args.all:
        years = None
    elif args.last:
        years = list(range(current_year - args.last + 1, current_year + 1))
    else:
        years = args.years or None

    analyze_strategy(years)


if __name__ == "__main__":
    main()
