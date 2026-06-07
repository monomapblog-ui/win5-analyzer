"""人気の和の分布分析

使い方:
  python analyze.py --year 2024
  python analyze.py --year 2023 --year 2024
  python analyze.py --all
"""
import asyncio
import argparse
from collections import Counter
from datetime import date

from sqlalchemy import select, func
from utils.db import init_db, AsyncSessionLocal, Win5Event


async def analyze(years: list[int] | None = None):
    await init_db()

    async with AsyncSessionLocal() as session:
        q = select(Win5Event).where(Win5Event.popularity_sum.is_not(None))
        if years:
            from sqlalchemy import extract
            q = q.where(extract("year", Win5Event.held_date).in_(years))
        result = await session.execute(q.order_by(Win5Event.held_date))
        events = result.scalars().all()

    if not events:
        print("データがありません。先に collect.py を実行してください。")
        return

    print(f"\n{'='*56}")
    print(f"  WIN5 人気の和 分布分析  （{len(events)} 開催）")
    print(f"{'='*56}")

    # ゾーン集計
    zone_count = Counter(e.zone for e in events)
    total = len(events)
    print(f"\n■ ゾーン別頻度")
    print(f"  low    (〜14)  : {zone_count['low']:3d}回  {zone_count['low']/total*100:5.1f}%")
    print(f"  target (15〜22): {zone_count['target']:3d}回  {zone_count['target']/total*100:5.1f}%  ← 狙い目")
    print(f"  high   (23〜)  : {zone_count['high']:3d}回  {zone_count['high']/total*100:5.1f}%")

    # 人気の和ごとの払戻平均
    print(f"\n■ 人気の和 × 払戻（的中回のみ）")
    print(f"  {'和':>3}  {'回数':>4}  {'平均払戻':>12}  {'最高払戻':>12}  {'最低払戻':>12}")
    print(f"  {'-'*50}")

    by_sum: dict[int, list[int]] = {}
    for e in events:
        if e.popularity_sum is not None and e.payout is not None:
            by_sum.setdefault(e.popularity_sum, []).append(e.payout)

    for s in sorted(by_sum.keys()):
        payouts = by_sum[s]
        avg = sum(payouts) // len(payouts)
        marker = " ★" if 15 <= s <= 22 else ""
        print(
            f"  {s:3d}  {len(payouts):4d}  "
            f"{avg:>12,}円  {max(payouts):>12,}円  {min(payouts):>12,}円{marker}"
        )

    # ターゲットゾーン詳細
    target_events = [e for e in events if e.zone == "target" and e.payout]
    if target_events:
        avg_payout = sum(e.payout for e in target_events) // len(target_events)
        print(f"\n■ ターゲットゾーン（15〜22）サマリ")
        print(f"  的中回数    : {len(target_events)}")
        print(f"  平均払戻    : {avg_payout:,}円")
        print(f"  最高払戻    : {max(e.payout for e in target_events):,}円")
        print(f"  最低払戻    : {min(e.payout for e in target_events):,}円")

    # 不的中（払戻なし）の分布
    no_hit = [e for e in events if e.payout is None]
    if no_hit:
        no_hit_sums = Counter(e.popularity_sum for e in no_hit if e.popularity_sum)
        print(f"\n■ 不的中開催の人気の和分布（上位10）")
        for s, cnt in no_hit_sums.most_common(10):
            zone = "target" if 15 <= s <= 22 else ("low" if s <= 14 else "high")
            print(f"  和={s:2d} ({zone:6s}): {cnt:3d}回")

    print()


def main():
    parser = argparse.ArgumentParser(description="WIN5人気の和 分布分析")
    parser.add_argument("--year", type=int, action="append", dest="years", metavar="YYYY")
    parser.add_argument("--all",  action="store_true", help="全年対象")
    args = parser.parse_args()
    years = None if args.all else (args.years or [date.today().year])
    asyncio.run(analyze(years))


if __name__ == "__main__":
    main()
