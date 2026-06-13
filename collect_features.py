"""WIN5 各スロットのレース特徴量を収集する

使い方:
  python collect_features.py          # 未収集分のみ
  python collect_features.py --force  # 全件再取得
  python collect_features.py --last 3 # 直近3年分
"""
import argparse
import time
from datetime import date

from sqlalchemy import select
from utils.db import init_db, SessionLocal, Win5Event, Win5Slot, Win5RaceFeature
from collectors.netkeiba import fetch_race_features


def collect_features(force: bool = False, years: list[int] | None = None):
    init_db()

    with SessionLocal() as session:
        q = select(Win5Slot).join(Win5Event).where(Win5Slot.race_id_str.is_not(None))
        if years:
            slots_all = session.execute(q).scalars().all()
            slots = [
                s for s in slots_all
                if s.event and s.event.held_date.year in years
            ]
        else:
            slots = session.execute(q).scalars().all()

    print(f"対象スロット: {len(slots)}件")

    done = 0
    skipped = 0
    errors = 0

    for slot in slots:
        race_id = slot.race_id_str
        if not race_id:
            continue

        with SessionLocal() as session:
            existing = session.execute(
                select(Win5RaceFeature).where(Win5RaceFeature.slot_id == slot.id)
            ).scalar_one_or_none()

            if existing and not force:
                skipped += 1
                continue

        try:
            feat = fetch_race_features(race_id)
        except Exception as e:
            print(f"  ✗ {race_id}: {e}")
            errors += 1
            continue

        with SessionLocal() as session:
            existing = session.execute(
                select(Win5RaceFeature).where(Win5RaceFeature.slot_id == slot.id)
            ).scalar_one_or_none()

            if existing:
                obj = existing
            else:
                obj = Win5RaceFeature(slot_id=slot.id)
                session.add(obj)

            obj.field_size      = feat["field_size"]
            obj.course_type     = feat["course_type"]
            obj.distance        = feat["distance"]
            obj.track_condition = feat["track_condition"]
            obj.fav1_odds       = feat["fav1_odds"]
            obj.fav2_odds       = feat["fav2_odds"]
            obj.winner_odds     = feat["winner_odds"]
            obj.winner_pop      = feat["winner_pop"]
            session.commit()

        done += 1
        print(f"  ✓ {race_id}  頭数={feat['field_size']}  "
              f"{feat['course_type']}{feat['distance']}m  "
              f"{feat['track_condition']}  "
              f"1人気={feat['fav1_odds']}倍  勝ち馬={feat['winner_odds']}倍({feat['winner_pop']}人気)")

        if done % 50 == 0:
            print(f"--- {done}件完了 ---")

    print(f"\n完了: 取得{done}件 / スキップ{skipped}件 / エラー{errors}件")


def main():
    parser = argparse.ArgumentParser(description="WIN5レース特徴量収集")
    parser.add_argument("--force", action="store_true", help="既存データも再取得")
    parser.add_argument("--last",  type=int, metavar="N", help="直近N年分")
    parser.add_argument("--year",  type=int, action="append", dest="years", metavar="YYYY")
    args = parser.parse_args()

    years = None
    if args.last:
        current = date.today().year
        years = list(range(current - args.last + 1, current + 1))
    elif args.years:
        years = args.years

    collect_features(force=args.force, years=years)


if __name__ == "__main__":
    main()
