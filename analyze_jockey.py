"""
WIN5 騎手信頼度分析スクリプト

指標:
  - 騎手別 WIN5対象レース 出走回数・勝率
  - 人気帯別（1-2番人気 / 3-5番 / 6番以上）の期待値
  - スロット別の信頼度ランキング
"""

from collections import defaultdict
from utils.db import init_db, SessionLocal, Win5Event, Win5Slot
from sqlalchemy import select


# ─────────────────────────────────────────────
# データ取得
# ─────────────────────────────────────────────

def fetch_data():
    """(slot_number, winner_jockey, winner_popularity, popularity_sum) を返す"""
    with SessionLocal() as session:
        stmt = (
            select(
                Win5Slot.slot_number,
                Win5Slot.winner_jockey,
                Win5Slot.winner_popularity,
                Win5Event.popularity_sum,
            )
            .join(Win5Event, Win5Slot.event_id == Win5Event.id)
            .where(Win5Slot.winner_jockey.isnot(None))
            .where(Win5Slot.winner_popularity.isnot(None))
        )
        return session.execute(stmt).all()


# ─────────────────────────────────────────────
# 分析
# ─────────────────────────────────────────────

def pop_bracket(pop):
    if pop <= 2:
        return "1-2番人気"
    elif pop <= 5:
        return "3-5番人気"
    else:
        return "6番人気以上"


def analyze_overall(rows):
    """騎手全体の勝率・出走回数"""
    wins   = defaultdict(int)
    total  = defaultdict(int)

    for slot_number, jockey, pop, psum in rows:
        total[jockey] += 1
        wins[jockey]  += 1  # 全行が勝ち馬なので常に1勝

    result = []
    for jockey, w in wins.items():
        t = total[jockey]
        result.append((jockey, t, w, w / t * 100))

    return sorted(result, key=lambda x: (-x[1], -x[2]))


def analyze_by_bracket(rows, min_rides=5):
    """騎手×人気帯 の勝率（出走5回以上）"""
    data = defaultdict(lambda: defaultdict(int))

    for slot_number, jockey, pop, psum in rows:
        bracket = pop_bracket(pop)
        data[jockey][bracket] += 1

    result = []
    for jockey, brackets in data.items():
        total_rides = sum(brackets.values())
        if total_rides < min_rides:
            continue
        result.append((
            jockey,
            total_rides,
            brackets.get("1-2番人気", 0),
            brackets.get("3-5番人気", 0),
            brackets.get("6番人気以上", 0),
        ))
    return sorted(result, key=lambda x: -x[1])


def analyze_by_slot(rows, min_rides=3):
    """スロット別 騎手勝利数ランキング（上位5件）"""
    slot_jockey = defaultdict(lambda: defaultdict(int))

    for slot_number, jockey, pop, psum in rows:
        slot_jockey[slot_number][jockey] += 1

    return {
        slot: sorted(d.items(), key=lambda x: -x[1])[:5]
        for slot, d in sorted(slot_jockey.items())
        if any(v >= min_rides for v in d.values())
    }


def analyze_upset_jockeys(rows, min_rides=3):
    """6番人気以上で勝った回数が多い穴騎手"""
    upset = defaultdict(int)
    total = defaultdict(int)

    for slot_number, jockey, pop, psum in rows:
        total[jockey] += 1
        if pop >= 6:
            upset[jockey] += 1

    result = []
    for jockey, u in upset.items():
        t = total[jockey]
        if t < min_rides:
            continue
        result.append((jockey, t, u, u / t * 100))

    return sorted(result, key=lambda x: -x[2])[:15]


# ─────────────────────────────────────────────
# 表示
# ─────────────────────────────────────────────

W = 72

def hr():
    print("=" * W)

def section(title):
    hr()
    print(f"  {title}")
    hr()


def print_overall(rows):
    section("騎手別 WIN5対象レース 勝利数ランキング (上位30件)")
    data = analyze_overall(rows)
    print(f"  {'騎手':<12}  {'勝利':>5}  {'TOP30内%':>8}")
    print("-" * W)
    for jockey, total, wins, pct in data[:30]:
        bar = "█" * min(int(wins / 2), 20)
        print(f"  {jockey:<12}  {wins:>5}回  {bar}")
    print()


def print_by_bracket(rows):
    section("騎手別 人気帯ごとの勝利内訳 (出走5回以上、上位20件)")
    data = analyze_by_bracket(rows)
    header = f"  {'騎手':<12}  {'合計':>4}  {'1-2番':>5}  {'3-5番':>5}  {'6番+':>5}"
    print(header)
    print("-" * W)
    for jockey, total, fav, mid, upset in data[:20]:
        fav_pct   = fav   / total * 100
        mid_pct   = mid   / total * 100
        upset_pct = upset / total * 100
        print(
            f"  {jockey:<12}  {total:>4}回"
            f"  {fav:>3}({fav_pct:>4.0f}%)"
            f"  {mid:>3}({mid_pct:>4.0f}%)"
            f"  {upset:>3}({upset_pct:>4.0f}%)"
        )
    print()


def print_by_slot(rows):
    section("スロット別 勝利数ランキング (上位5騎手)")
    data = analyze_by_slot(rows)
    for slot, ranking in data.items():
        print(f"\n  【スロット {slot}】")
        for i, (jockey, wins) in enumerate(ranking, 1):
            bar = "█" * wins
            print(f"    {i}位  {jockey:<12}  {wins}勝  {bar}")
    print()


def print_upset_jockeys(rows):
    section("穴騎手ランキング (6番人気以上での勝利回数、出走3回以上)")
    data = analyze_upset_jockeys(rows)
    print(f"  {'騎手':<12}  {'穴勝利':>6}  {'全勝利':>6}  {'穴率':>6}")
    print("-" * W)
    for jockey, total, upset, pct in data:
        print(f"  {jockey:<12}  {upset:>6}回  {total:>6}回  {pct:>5.1f}%")
    print()


def print_summary(rows):
    section("サマリー: 信頼度の高い騎手ガイド")
    overall = analyze_overall(rows)
    bracket = analyze_by_bracket(rows)

    # 1-2番人気での勝率が高い「鉄板騎手」（実力馬を確実に勝たせる）
    fav_strong = []
    for jockey, total, fav, mid, upset in bracket:
        if total >= 5 and fav >= 3:
            fav_pct = fav / total * 100
            fav_strong.append((jockey, total, fav, fav_pct))
    fav_strong = sorted(fav_strong, key=lambda x: -x[3])[:10]

    print("  ▶ 1-2番人気で特に強い騎手（軸候補）")
    for jockey, total, fav, pct in fav_strong[:5]:
        print(f"    {jockey:<12}  1-2番人気勝利 {fav}回 / 全{total}回 ({pct:.0f}%)")

    print()
    upset_data = analyze_upset_jockeys(rows)
    print("  ▶ 穴で来やすい騎手（中穴候補）")
    for jockey, total, upset, pct in upset_data[:5]:
        print(f"    {jockey:<12}  穴勝利 {upset}回 / 全{total}回 ({pct:.0f}%)")
    print()


# ─────────────────────────────────────────────
# main
# ─────────────────────────────────────────────

if __name__ == "__main__":
    init_db()

    rows = fetch_data()
    if not rows:
        print("騎手データが見つかりません。")
        print("collect.py でレース結果を収集してから実行してください。")
        raise SystemExit(1)

    print(f"\nデータ: {len(rows)} スロット / 騎手データあり\n")

    print_overall(rows)
    print_by_bracket(rows)
    print_by_slot(rows)
    print_upset_jockeys(rows)
    print_summary(rows)
