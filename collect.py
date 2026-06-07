"""WIN5データ収集パイプライン（同期版）

使い方:
  python collect.py --last 6              # 過去6年分を一括収集
  python collect.py --year 2024           # 2024年のみ
  python collect.py --year 2023 --year 2024
  python collect.py --last 6 --list-only  # 開催一覧のみ（高速）
  python collect.py --last 6 --force      # 全データを再取得
"""
import argparse
import logging
from datetime import date

from sqlalchemy import select

from utils.db import init_db, SessionLocal, Race, Horse, Entry, Win5Event, Win5Slot
from collectors.netkeiba import (
    fetch_win5_list,
    fetch_win5_detail,
    fetch_race_result,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# メイン収集フロー
# ─────────────────────────────────────────────

def collect_year(year: int, list_only: bool = False, force: bool = False):
    init_db()
    log.info(f"=== {year}年 WIN5データ収集開始 ===")

    try:
        win5_list = fetch_win5_list(year)
    except Exception as e:
        log.error(f"WIN5一覧の取得に失敗しました: {e}")
        return

    log.info(f"WIN5開催: {len(win5_list)} 件")
    if not win5_list:
        log.warning("データが取得できませんでした。")
        return

    with SessionLocal() as session:
        for item in win5_list:
            held_date = item["held_date"]

            existing = session.scalar(
                select(Win5Event).where(Win5Event.held_date == held_date)
            )
            if existing and not force:
                log.info(f"  {held_date} スキップ（既存）")
                continue

            log.info(f"  {held_date} 処理中...")

            try:
                detail = fetch_win5_detail(held_date)
            except Exception as e:
                log.warning(f"  {held_date} 詳細取得失敗: {e}")
                detail = {
                    "slots":      _slots_from_list(item),
                    "payout":     item.get("payout"),
                    "unit_count": item.get("unit_count"),
                }

            payout     = detail.get("payout")     or item.get("payout")
            unit_count = detail.get("unit_count") or item.get("unit_count")

            if existing:
                event = existing
                event.payout     = payout
                event.unit_count = unit_count
            else:
                event = Win5Event(
                    held_date=held_date,
                    payout=payout,
                    unit_count=unit_count,
                )
                session.add(event)
                session.flush()

            for s in (detail.get("slots") or _slots_from_list(item)):
                slot_num = s["slot_number"]
                slot = session.scalar(
                    select(Win5Slot).where(
                        Win5Slot.event_id    == event.id,
                        Win5Slot.slot_number == slot_num,
                    )
                )
                if slot is None:
                    slot = Win5Slot(event_id=event.id, slot_number=slot_num)
                    session.add(slot)

                slot.race_id_str       = s.get("race_id")
                slot.winner_horse_name = s.get("winner_horse_name")
                slot.winner_popularity = s.get("winner_popularity")

            session.flush()
            session.refresh(event)
            event.calc_popularity_sum()
            session.commit()

            payout_str = f"{payout:,}円" if payout else "不的中"
            log.info(
                f"  {held_date} 保存完了 "
                f"払戻={payout_str} "
                f"人気の和={event.popularity_sum} zone={event.zone}"
            )

    if list_only:
        log.info("=== 一覧収集完了（--list-only のためレース結果はスキップ） ===")
        return

    collect_race_results(year, force)


def collect_race_results(year: int, force: bool = False):
    log.info(f"=== {year}年 レース結果収集開始 ===")

    with SessionLocal() as session:
        from sqlalchemy import extract
        result = session.execute(
            select(Win5Slot)
            .join(Win5Event)
            .where(extract("year", Win5Event.held_date) == year)
        )
        slots = result.scalars().all()
        race_ids = list({s.race_id_str for s in slots if s.race_id_str})

    log.info(f"対象レース: {len(race_ids)} 件")

    for race_id in race_ids:
        with SessionLocal() as session:
            existing = session.scalar(select(Race).where(Race.race_id == race_id))
            if existing and not force:
                log.info(f"  {race_id} スキップ（既存）")
                continue

        log.info(f"  {race_id} 取得中...")
        try:
            result = fetch_race_result(race_id)
        except Exception as e:
            log.warning(f"  {race_id} 取得失敗: {e}")
            continue

        _save_race_result(race_id, result["entries"])
        _link_slot_to_race(race_id)

    log.info("=== レース結果収集完了 ===")


def _save_race_result(race_id: str, entries: list[dict]):
    if not entries:
        return

    with SessionLocal() as session:
        race = session.scalar(select(Race).where(Race.race_id == race_id))
        if race is None:
            race = Race(
                race_id=race_id,
                held_date=date(int(race_id[:4]), int(race_id[4:6]), int(race_id[6:8])),
                venue=_venue_from_race_id(race_id),
                race_number=int(race_id[10:12]),
            )
            session.add(race)
            session.flush()

        for e in entries:
            if not e.get("horse_name"):
                continue

            horse_id_str = e.get("horse_id")
            horse = None
            if horse_id_str:
                horse = session.scalar(select(Horse).where(Horse.horse_id == horse_id_str))
            if horse is None:
                horse = Horse(
                    horse_id=horse_id_str or f"unknown_{race_id}_{e.get('horse_number')}",
                    name=e["horse_name"],
                )
                session.add(horse)
                session.flush()

            entry = session.scalar(
                select(Entry).where(
                    Entry.race_id      == race.id,
                    Entry.horse_number == e.get("horse_number"),
                )
            )
            if entry is None:
                entry = Entry(race_id=race.id, horse_id=horse.id)
                session.add(entry)

            entry.horse_number    = e.get("horse_number")
            entry.frame_number    = e.get("frame_number")
            entry.popularity      = e.get("popularity")
            entry.odds            = e.get("odds")
            entry.finish_position = e.get("finish_position")

        session.commit()
        log.info(f"    {race_id} 保存: {len(entries)} 頭")


def _link_slot_to_race(race_id_str: str):
    with SessionLocal() as session:
        race = session.scalar(select(Race).where(Race.race_id == race_id_str))
        if race is None:
            return

        slots = session.execute(
            select(Win5Slot).where(Win5Slot.race_id_str == race_id_str)
        ).scalars().all()

        for slot in slots:
            slot.race_id = race.id
            if slot.winner_popularity is None:
                winner_entry = session.scalar(
                    select(Entry).where(
                        Entry.race_id         == race.id,
                        Entry.finish_position == 1,
                    )
                )
                if winner_entry:
                    slot.winner_popularity = winner_entry.popularity
            if slot.winner_horse_id is None:
                winner_entry = session.scalar(
                    select(Entry).where(
                        Entry.race_id         == race.id,
                        Entry.finish_position == 1,
                    )
                )
                if winner_entry:
                    slot.winner_horse_id = winner_entry.horse_id

        session.commit()

    # 人気の和を再計算
    with SessionLocal() as session:
        slot = session.scalar(
            select(Win5Slot).where(Win5Slot.race_id_str == race_id_str)
        )
        if slot:
            event = session.get(Win5Event, slot.event_id)
            if event:
                session.refresh(event)
                event.calc_popularity_sum()
                session.commit()
                log.info(
                    f"    人気の和更新: {event.held_date} "
                    f"sum={event.popularity_sum} zone={event.zone}"
                )


# ─────────────────────────────────────────────
# ヘルパー
# ─────────────────────────────────────────────

def _slots_from_list(item: dict) -> list[dict]:
    return [
        {"slot_number": i, "race_id": rid,
         "winner_horse_name": None, "winner_popularity": None}
        for i, rid in enumerate(item.get("race_ids", []), start=1)
    ]


_VENUE_CODE = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟",
    "05": "東京", "06": "中山", "07": "中京", "08": "京都",
    "09": "阪神", "10": "小倉",
}

def _venue_from_race_id(race_id: str) -> str | None:
    if len(race_id) == 12:
        return _VENUE_CODE.get(race_id[4:6])
    return None


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="WIN5データ収集パイプライン",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python collect.py --last 6              # 過去6年分を一括収集
  python collect.py --year 2024           # 2024年のみ
  python collect.py --year 2023 --year 2024
  python collect.py --last 6 --list-only  # 開催一覧のみ（高速）
  python collect.py --last 6 --force      # 全データを再取得
        """,
    )
    parser.add_argument("--year",      type=int, action="append", dest="years",
                        metavar="YYYY", help="収集対象年（複数指定可）")
    parser.add_argument("--last",      type=int, metavar="N",
                        help="現在年から遡ってN年分（例: --last 6）")
    parser.add_argument("--list-only", action="store_true",
                        help="WIN5開催一覧のみ収集")
    parser.add_argument("--force",     action="store_true",
                        help="既存データを上書き再取得")
    args = parser.parse_args()

    current_year = date.today().year
    if args.last:
        years = list(range(current_year - args.last + 1, current_year + 1))
    elif args.years:
        years = sorted(set(args.years))
    else:
        years = [current_year]

    log.info(f"収集対象年: {years}")
    for year in years:
        collect_year(year, list_only=args.list_only, force=args.force)


if __name__ == "__main__":
    main()
