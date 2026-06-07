"""WIN5データ収集パイプライン

使い方:
  python collect.py --last 6              # 過去6年分を一括収集
  python collect.py --year 2024           # 2024年のみ
  python collect.py --last 6 --list-only  # 開催一覧のみ（高速・人気不要）
  python collect.py --last 6 --force      # 全データを再取得
"""
import argparse
import logging
from datetime import date

from sqlalchemy import select, extract

from utils.db import init_db, SessionLocal, Race, Horse, Entry, Win5Event, Win5Slot
from collectors.netkeiba import fetch_win5_dates, fetch_win5_by_date, fetch_race_result

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def collect_year(year: int, list_only: bool = False, force: bool = False):
    init_db()
    log.info(f"=== {year}年 WIN5データ収集開始 ===")

    # 対象年の全日付を取得
    try:
        all_dates = fetch_win5_dates(target_years=[year])
    except Exception as e:
        log.error(f"日付一覧の取得に失敗: {e}")
        return

    log.info(f"WIN5開催日: {len(all_dates)} 件")
    if not all_dates:
        log.warning(f"{year}年のデータが見つかりませんでした。")
        return

    # 各日付の詳細を収集
    for date_str in all_dates:
        with SessionLocal() as session:
            held_date = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
            existing = session.scalar(
                select(Win5Event).where(Win5Event.held_date == held_date)
            )
            if existing and not force:
                log.info(f"  {date_str} スキップ（既存）")
                continue

        log.info(f"  {date_str} 取得中...")
        try:
            data = fetch_win5_by_date(date_str)
        except Exception as e:
            log.warning(f"  {date_str} 取得失敗: {e}")
            continue

        if data is None:
            log.info(f"  {date_str} データなし（スキップ）")
            continue

        _save_win5_event(data, force)

    if list_only:
        log.info(f"=== {year}年 一覧収集完了（--list-only のためレース結果はスキップ） ===")
        return

    # レース結果を取得して人気の和を確定させる
    _collect_race_results_for_year(year, force)
    log.info(f"=== {year}年 収集完了 ===")


def _save_win5_event(data: dict, force: bool = False):
    """Win5Event + Win5Slot を保存する"""
    held_date  = data["held_date"]
    payout     = data.get("payout")
    unit_count = data.get("unit_count")

    with SessionLocal() as session:
        existing = session.scalar(
            select(Win5Event).where(Win5Event.held_date == held_date)
        )
        if existing and force:
            session.delete(existing)
            session.commit()
            existing = None

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

        for s in data.get("slots", []):
            slot = session.scalar(
                select(Win5Slot).where(
                    Win5Slot.event_id    == event.id,
                    Win5Slot.slot_number == s["slot_number"],
                )
            )
            if slot is None:
                slot = Win5Slot(event_id=event.id, slot_number=s["slot_number"])
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
        f"  {held_date} 保存完了  払戻={payout_str}  "
        f"人気の和={event.popularity_sum}  zone={event.zone}"
    )


def _collect_race_results_for_year(year: int, force: bool = False):
    """指定年のWin5Slotに紐づく全レース結果を取得・保存し、勝ち馬人気を補完する"""
    log.info(f"  レース結果収集中（{year}年）...")

    with SessionLocal() as session:
        slots = session.execute(
            select(Win5Slot)
            .join(Win5Event)
            .where(extract("year", Win5Event.held_date) == year)
            .where(Win5Slot.race_id_str.is_not(None))
        ).scalars().all()
        race_ids = list({s.race_id_str for s in slots})

    log.info(f"  対象レース: {len(race_ids)} 件")

    for race_id in race_ids:
        with SessionLocal() as session:
            existing = session.scalar(select(Race).where(Race.race_id == race_id))
            if existing and not force:
                continue

        log.info(f"    {race_id} 取得中...")
        try:
            result = fetch_race_result(race_id)
        except Exception as e:
            log.warning(f"    {race_id} 取得失敗: {e}")
            continue

        if not result["entries"]:
            log.warning(f"    {race_id} エントリーなし（HTML構造要確認）")
            continue

        _save_race_and_update_popularity(race_id, result["entries"])


def _save_race_and_update_popularity(race_id: str, entries: list[dict]):
    """レース結果を保存し、Win5Slotの勝ち馬人気を更新する"""
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

        winner_popularity = None
        winner_horse_id   = None

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

            if e.get("finish_position") == 1:
                winner_popularity = e.get("popularity")
                winner_horse_id   = horse.id

        session.flush()

        # Win5Slotに勝ち馬人気を反映
        slots = session.execute(
            select(Win5Slot).where(Win5Slot.race_id_str == race_id)
        ).scalars().all()
        for slot in slots:
            slot.race_id = race.id
            if winner_popularity is not None:
                slot.winner_popularity = winner_popularity
            if winner_horse_id is not None:
                slot.winner_horse_id = winner_horse_id

        session.commit()
        log.info(f"    {race_id} 保存完了（{len(entries)}頭 勝ち馬人気={winner_popularity}）")

    # 人気の和を再計算（全スロットを直接クエリして確実に集計）
    with SessionLocal() as session:
        slot = session.scalar(
            select(Win5Slot).where(Win5Slot.race_id_str == race_id)
        )
        if slot:
            event = session.get(Win5Event, slot.event_id)
            if event:
                all_slots = session.execute(
                    select(Win5Slot).where(Win5Slot.event_id == event.id)
                ).scalars().all()
                pops = [s.winner_popularity for s in all_slots if s.winner_popularity is not None]
                event.popularity_sum = sum(pops) if len(pops) == 5 else None
                session.commit()
                log.info(
                    f"    人気の和更新: {event.held_date}  "
                    f"sum={event.popularity_sum}  zone={event.zone}"
                )


# ─────────────────────────────────────────────
# ヘルパー
# ─────────────────────────────────────────────

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
    parser.add_argument("--year",      type=int, action="append", dest="years", metavar="YYYY")
    parser.add_argument("--last",      type=int, metavar="N")
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--force",     action="store_true")
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
