"""
WIN5 スロット別人気分析スクリプト
各スロット(1-5)の勝ち馬人気の分布・累積勝率・推奨レンジを出力する。
"""

from collections import defaultdict
from utils.db import init_db, SessionLocal, Win5Event, Win5Slot
from sqlalchemy import select

# ─────────────────────────────────────────────
# データ取得
# ─────────────────────────────────────────────

def fetch_data():
    """(event_id, slot_number, winner_popularity, popularity_sum) のリストを返す"""
    with SessionLocal() as session:
        stmt = (
            select(
                Win5Slot.event_id,
                Win5Slot.slot_number,
                Win5Slot.winner_popularity,
                Win5Event.popularity_sum,
            )
            .join(Win5Event, Win5Slot.event_id == Win5Event.id)
            .where(Win5Slot.winner_popularity.isnot(None))
            .order_by(Win5Event.held_date, Win5Slot.slot_number)
        )
        rows = session.execute(stmt).all()
    return rows


# ─────────────────────────────────────────────
# ヘルパー
# ─────────────────────────────────────────────

def zone_label(popularity_sum):
    if popularity_sum is None:
        return "unknown"
    if popularity_sum <= 14:
        return "low"
    elif popularity_sum <= 22:
        return "target"
    else:
        return "high"


def analyze_slot_distribution(rows):
    """スロット -> [winner_popularity] の辞書を返す"""
    slot_pops = defaultdict(list)
    for event_id, slot_number, winner_popularity, popularity_sum in rows:
        slot_pops[slot_number].append(winner_popularity)
    return slot_pops


def build_distribution(pops):
    dist = defaultdict(int)
    for p in pops:
        dist[p] += 1
    return dist


def cumulative_rate(dist, total, up_to):
    count = sum(dist.get(i, 0) for i in range(1, up_to + 1))
    return count / total if total > 0 else 0.0


def coverage_range_for_target(dist, total, target=0.70):
    """1番人気から順に積み上げてtargetを超えた人気番号と実際の率を返す"""
    cumsum = 0
    for pop in range(1, 20):
        cumsum += dist.get(pop, 0)
        rate = cumsum / total
        if rate >= target:
            return pop, rate
    return 19, cumsum / total


# ─────────────────────────────────────────────
# 出力定数
# ─────────────────────────────────────────────

DIVIDER = "=" * 72
THIN    = "-" * 72


# ─────────────────────────────────────────────
# スロット別詳細分析
# ─────────────────────────────────────────────

def print_slot_analysis(slot_pops):
    print(DIVIDER)
    print("  WIN5 スロット別 勝ち馬人気 分析")
    print(DIVIDER)

    summary_rows = []

    for slot in range(1, 6):
        pops = slot_pops.get(slot, [])
        n = len(pops)
        if n == 0:
            print(f"\n[スロット {slot}] データなし\n")
            continue

        dist = build_distribution(pops)
        avg  = sum(pops) / n

        print(f"\n【スロット {slot}】  サンプル数: {n}  平均人気: {avg:.2f}")
        print(THIN)

        # 分布テーブル
        print(f"  {'人気':>4}  {'回数':>5}  {'割合':>6}  {'累積':>7}  バー")
        print(f"  {'-'*4}  {'-'*5}  {'-'*6}  {'-'*7}  {'-'*30}")

        cumsum = 0
        for pop in sorted(dist.keys()):
            cnt  = dist[pop]
            rate = cnt / n
            cumsum += cnt
            cum_rate = cumsum / n
            bar  = "█" * int(rate * 30)
            print(f"  {pop:>4}番  {cnt:>5}回  {rate:>5.1%}  {cum_rate:>6.1%}  {bar}")

        # 累積勝率
        print()
        print("  累積勝率:")
        for up_to in [2, 3, 4, 5, 6, 8, 10]:
            rate = cumulative_rate(dist, n, up_to)
            bar  = "▓" * int(rate * 30)
            print(f"    1〜{up_to:>2}番人気  {rate:>6.1%}  {bar}")

        # 70%カバーレンジ
        max_pop, rate_70 = coverage_range_for_target(dist, n, 0.70)
        print()
        print(f"  ▶ 70%カバーに必要な人気レンジ: 1〜{max_pop}番人気  ({rate_70:.1%})")
        summary_rows.append((slot, avg, max_pop, rate_70))

    return summary_rows


# ─────────────────────────────────────────────
# サマリーテーブル
# ─────────────────────────────────────────────

def print_summary_table(summary_rows):
    print(f"\n{DIVIDER}")
    print("  サマリー: スロット別 推奨人気レンジ (70%カバー基準)")
    print(DIVIDER)
    print(f"  {'スロット':^6}  {'平均人気':^8}  {'推奨レンジ':^14}  {'実際カバー率':^12}")
    print(f"  {'-'*6}  {'-'*8}  {'-'*14}  {'-'*12}")
    for slot, avg, max_pop, rate_70 in summary_rows:
        rng = f"1〜{max_pop}番人気"
        print(f"  {slot:^6}  {avg:^8.2f}  {rng:^14}  {rate_70:^12.1%}")
    print()


# ─────────────────────────────────────────────
# クロススロット分析
# ─────────────────────────────────────────────

def cross_slot_analysis(rows):
    # event_id -> {slot: popularity}
    events = defaultdict(dict)
    for event_id, slot_number, winner_popularity, popularity_sum in rows:
        events[event_id][slot_number] = winner_popularity

    # スロット1の堅い/荒れでグループ化
    groups = {
        "堅い (1-2番人気)": defaultdict(list),
        "荒れ (3番人気以上)": defaultdict(list),
    }
    for event_id, slot_data in events.items():
        if slot_data.get(1) is None:
            continue
        s1_pop = slot_data[1]
        label  = "堅い (1-2番人気)" if s1_pop <= 2 else "荒れ (3番人気以上)"
        for s in range(1, 6):
            if slot_data.get(s) is not None:
                groups[label][s].append(slot_data[s])

    print(f"{DIVIDER}")
    print("  クロススロット分析: スロット1が堅い/荒れた時の他スロットへの影響")
    print(DIVIDER)
    print()

    for label, slot_lists in groups.items():
        n_events = len(slot_lists.get(1, []))
        print(f"  ■ スロット1 = {label}  (イベント数: {n_events})")
        print(f"    {'スロット':^6}  {'平均人気':^8}  {'1-2番率':^8}  {'3番以上率':^10}  {'5番以上率':^10}")
        print(f"    {'-'*6}  {'-'*8}  {'-'*8}  {'-'*10}  {'-'*10}")
        for slot in range(1, 6):
            pops = slot_lists.get(slot, [])
            if not pops:
                continue
            n   = len(pops)
            avg = sum(pops) / n
            r12 = sum(1 for p in pops if p <= 2) / n
            r3p = sum(1 for p in pops if p >= 3) / n
            r5p = sum(1 for p in pops if p >= 5) / n
            marker = " ← S1" if slot == 1 else ""
            print(f"    {slot:^6}  {avg:^8.2f}  {r12:^8.1%}  {r3p:^10.1%}  {r5p:^10.1%}{marker}")
        print()

    # 荒れ連鎖マトリクス: 各スロットが荒れた時の他スロット平均人気
    all_complete = {eid: sd for eid, sd in events.items()
                    if all(sd.get(s) is not None for s in range(1, 6))}

    print(f"  ■ 荒れ連鎖マトリクス")
    print(f"     (各スロットで3番人気以上が勝った場合の、他スロット平均人気の変化)")
    print()
    print(f"    {'スロット':^6}  {'堅い時(他平均)':^14}  {'荒れ時(他平均)':^14}  {'差':^6}  判定")
    print(f"    {'-'*6}  {'-'*14}  {'-'*14}  {'-'*6}  {'-'*10}")

    for anchor in range(1, 6):
        solid_others = []
        upset_others = []
        for eid, sd in all_complete.items():
            other_pops = [sd[s] for s in range(1, 6) if s != anchor]
            other_avg  = sum(other_pops) / len(other_pops)
            if sd[anchor] <= 2:
                solid_others.append(other_avg)
            else:
                upset_others.append(other_avg)

        s_avg = sum(solid_others) / len(solid_others) if solid_others else float("nan")
        u_avg = sum(upset_others) / len(upset_others) if upset_others else float("nan")
        diff  = u_avg - s_avg if (solid_others and upset_others) else float("nan")

        if diff != diff:  # nan check
            trend = "データ不足"
        elif diff > 0.5:
            trend = "↑荒れ連鎖強"
        elif diff > 0.2:
            trend = "↑荒れ連鎖弱"
        elif diff < -0.5:
            trend = "↓堅さ連鎖強"
        elif diff < -0.2:
            trend = "↓堅さ連鎖弱"
        else:
            trend = "→影響ほぼなし"

        print(f"    {anchor:^6}  {s_avg:^14.2f}  {u_avg:^14.2f}  {diff:^+6.2f}  {trend}")
    print()


# ─────────────────────────────────────────────
# ゾーン別分析
# ─────────────────────────────────────────────

def zone_analysis(rows):
    zone_slot = defaultdict(lambda: defaultdict(list))
    for event_id, slot_number, winner_popularity, popularity_sum in rows:
        z = zone_label(popularity_sum)
        zone_slot[z][slot_number].append(winner_popularity)

    print(DIVIDER)
    print("  ゾーン別分析  (low: 合計≦14 / target: 15-22 / high: ≧23)")
    print(DIVIDER)
    print(f"  {'ゾーン':^8}  {'S1':^6}  {'S2':^6}  {'S3':^6}  {'S4':^6}  {'S5':^6}  {'件数':^6}")
    print(f"  {'-'*8}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*6}")

    for z in ["low", "target", "high"]:
        slot_data = zone_slot.get(z, {})
        avgs = []
        n_ev = 0
        for s in range(1, 6):
            pops = slot_data.get(s, [])
            n_ev = max(n_ev, len(pops))
            avgs.append(f"{sum(pops)/len(pops):.2f}" if pops else "  -  ")
        print(f"  {z:^8}  {'  '.join(f'{a:^6}' for a in avgs)}  {n_ev:^6}")
    print()


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────

def main():
    init_db()
    rows = fetch_data()

    if not rows:
        print("データが見つかりません。まず scraper を実行してください。")
        return

    total_events = len(set(r[0] for r in rows))
    print(f"\nデータ概要: {total_events} イベント / {len(rows)} スロットレコード\n")

    slot_pops    = analyze_slot_distribution(rows)
    summary_rows = print_slot_analysis(slot_pops)
    print_summary_table(summary_rows)
    cross_slot_analysis(rows)
    zone_analysis(rows)

    # 最終推奨
    print(DIVIDER)
    print("  【最終推奨】 券種選択ガイド")
    print(DIVIDER)
    print()
    print("  目標: 各スロットで70%カバー → 購入点数を最小化")
    print()
    for slot, avg, max_pop, rate_70 in summary_rows:
        print(f"  スロット{slot}: 1〜{max_pop}番人気  ({rate_70:.0%}カバー)  → {max_pop}頭選択")

    total_combinations = 1
    for _, _, max_pop, _ in summary_rows:
        total_combinations *= max_pop
    print()
    print(f"  全スロット推奨レンジの組み合わせ数: {total_combinations:,} 通り")
    print()
    print("  ※ 点数削減のコツ:")
    print("    - 当日単勝オッズを確認し、抜けた1番人気は1頭に絞る")
    print("    - クロス分析で荒れ連鎖が強いスロットは推奨レンジ+1番人気まで広げる")
    print("    - popularity_sum のゾーン予測と組み合わせてフィルタリングする")
    print()


if __name__ == "__main__":
    main()
