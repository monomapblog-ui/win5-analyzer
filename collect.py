"""収集パイプライン エントリーポイント

使い方:
  python collect.py --year 2024           # 2024年のWIN5結果を収集
  python collect.py --year 2024 --races   # 各レース結果も収集
"""
import asyncio
import argparse
from datetime import date

from utils.db import init_db, AsyncSessionLocal, Win5Result, Win5Slot
from collectors.netkeiba import fetch_win5_results
from sqlalchemy import select


async def collect_win5_year(year: int, include_races: bool = False):
    await init_db()
    print(f"[collect] {year}年のWIN5結果を収集中...")

    results = await fetch_win5_results(year)
    print(f"[collect] {len(results)} 件取得")

    async with AsyncSessionLocal() as session:
        for r in results:
            existing = await session.scalar(
                select(Win5Result).where(Win5Result.held_date == r["held_date"])
            )
            if existing:
                continue
            session.add(Win5Result(
                held_date=r["held_date"],
                payout=r.get("payout"),
                unit_count=r.get("unit_count"),
            ))
        await session.commit()

    print("[collect] DB保存完了")


def main():
    parser = argparse.ArgumentParser(description="WIN5データ収集")
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--races", action="store_true", help="各レース結果も収集")
    args = parser.parse_args()

    asyncio.run(collect_win5_year(args.year, args.races))


if __name__ == "__main__":
    main()
