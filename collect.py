"""WIN5データ収集パイプライン

使い方:
  # 指定年のWIN5開催一覧 + 各レース結果を収集
  python collect.py --year 2024

  # 複数年
  python collect.py --year 2023 --year 2024

  # 一覧のみ（レース結果を取りに行かない）
  python collect.py --year 2024 --list-only

  # 既存データをスキップせず再取得
  python collect.py --year 2024 --force
"""
import asyncio
import argparse
import logging
from datetime import date

from sqlalchemy import select

from utils.db import (
    init_db, AsyncSessionLocal,
    Race, Horse, Entry, Win5Event, Win5Slot,
)
from collectors.netkeiba import (
    fetch_win5_list,
    fetch_win5_detail,
    fetch_race_result,
    fetch_horse_profile,
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

async def collect_year(year: int, list_only: bool = False, force: bool = False):
    await init_db()
    log.info(f"=== {year}年 WIN5データ収集開始 ===")

    win5_list = await fetch_win5_list(year)
    log.info(f"WIN5開催: {len(win5_list)} 件")

    if not win5_list:
        log.warning("データが取得できませんでした。ネットワーク接続・URLを確認してください。")
        return

    async with AsyncSessionLocal() as session:
        for item in win5_list:
            held_date = item["held_date"]

            # 既存チェック
            existing = await session.scalar(
                select(Win5Event).where(Win5Event.held_date == held_date)
            )
            if existing and not force:
                log.info(f"  {held_date} スキップ（既存）")
                continue

            log.info(f"  {held_date} 処理中...")

            # WIN5詳細（各スロットの勝ち馬人気など）
            try:
                detail = await fetch_win5_detail(held_date)
            except Exception as e:
                log.warning(f"  {held_date} 詳細取得失敗: {e}")
                detail = {"slots": [], "payout": item.get("payout"), "unit_count": item.get("unit_count")}

            # payout / unit_count は一覧か詳細のどちらかから
            payout     = detail.get("payout")     or item.get("payout")
            unit_count = detail.get("unit_count") or item.get("unit_count")

            # Win5Event 保存
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
                await session.flush()  # IDを確定

            # Win5Slot 保存
            slots_data = detail.get("slots") or _slots_from_list(item)
            for s in slots_data:
                slot_num = s["slot_number"]
                slot = await session.scalar(
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

            await session.flush()

            # 人気の和を計算
            await session.refresh(event, ["slots"])
            event.calc_popularity_sum()

            await session.commit()
            log.info(
                f"  {held_date} 保存完了 "
                f"払戻={payout:,}円 " if payout else f"  {held_date} 保存完了 払戻=不的中 "
                + f"人気の和={event.popularity_sum} zone={event.zone}"
            )

    if list_only:
        log.info("=== 一覧収集完了（--list-only のためレース結果はスキップ） ===")
        return

    # レース結果の詳細収集
    await collect_race_results(year, force)


async def collect_race_results(year: int, force: bool = False):
    """Win5Slotに紐づく各レースの結果を収集してDBに保存する"""
    log.info(f"=== {year}年 レース結果収集開始 ===")

    async with AsyncSessionLocal() as session:
        # 対象スロット: race_id_strがあってRaceレコードがまだないもの
        result = await session.execute(
            select(Win5Slot)
            .join(Win5Event)
            .where(Win5Event.held_date.between(date(year, 1, 1), date(year, 12, 31)))
        )
        slots = result.scalars().all()

    race_ids = list({s.race_id_str for s in slots if s.race_id_str})
    log.info(f"対象レース: {len(race_ids)} 件")

    for race_id in race_ids:
        async with AsyncSessionLocal() as session:
            existing_race = await session.scalar(
                select(Race).where(Race.race_id == race_id)
            )
            if existing_race and not force:
                log.info(f"  {race_id} スキップ（既存）")
                continue

        log.info(f"  {race_id} 取得中...")
        try:
            result = await fetch_race_result(race_id)
        except Exception as e:
            log.warning(f"  {race_id} 取得失敗: {e}")
            continue

        await _save_race_result(race_id, result["entries"])

        # Win5Slotにrace_id（FK）を紐付け
        await _link_slot_to_race(race_id)

    log.info("=== レース結果収集完了 ===")


async def _save_race_result(race_id: str, entries: list[dict]):
    """レース結果をRace・Horse・Entryに保存する"""
    if not entries:
        return

    async with AsyncSessionLocal() as session:
        # Race
        race = await session.scalar(select(Race).where(Race.race_id == race_id))
        if race is None:
            race = Race(
                race_id=race_id,
                held_date=date(int(race_id[:4]), int(race_id[4:6]), int(race_id[6:8])),
                venue=_venue_from_race_id(race_id),
                race_number=int(race_id[10:12]),
            )
            session.add(race)
            await session.flush()

        for e in entries:
            if not e.get("horse_name"):
                continue

            # Horse（未登録なら新規）
            horse_id_str = e.get("horse_id")
            horse = None
            if horse_id_str:
                horse = await session.scalar(
                    select(Horse).where(Horse.horse_id == horse_id_str)
                )
            if horse is None:
                horse = Horse(
                    horse_id=horse_id_str or f"unknown_{race_id}_{e.get('horse_number')}",
                    name=e["horse_name"],
                )
                session.add(horse)
                await session.flush()

            # Entry
            entry = await session.scalar(
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

        await session.commit()
        log.info(f"    {race_id} 保存: {len(entries)} 頭")


async def _link_slot_to_race(race_id_str: str):
    """Win5SlotのFK(race_id)をRaceのIDに紐付ける"""
    async with AsyncSessionLocal() as session:
        race = await session.scalar(select(Race).where(Race.race_id == race_id_str))
        if race is None:
            return
        slots = (await session.execute(
            select(Win5Slot).where(Win5Slot.race_id_str == race_id_str)
        )).scalars().all()
        for slot in slots:
            # 勝ち馬の人気を Entry から補完
            if slot.winner_popularity is None:
                winner_entry = await session.scalar(
                    select(Entry).where(
                        Entry.race_id         == race.id,
                        Entry.finish_position == 1,
                    )
                )
                if winner_entry:
                    slot.winner_popularity = winner_entry.popularity

            slot.race_id = race.id

            # 勝ち馬の Horse FK も紐付け
            if slot.winner_horse_name and slot.winner_horse_id is None:
                winner_entry = await session.scalar(
                    select(Entry).where(
                        Entry.race_id         == race.id,
                        Entry.finish_position == 1,
                    )
                )
                if winner_entry:
                    slot.winner_horse_id = winner_entry.horse_id

        await session.commit()

    # Win5Event の人気の和を再計算
    async with AsyncSessionLocal() as session:
        slot = await session.scalar(
            select(Win5Slot).where(Win5Slot.race_id_str == race_id_str)
        )
        if slot:
            event = await session.get(Win5Event, slot.event_id)
            if event:
                await session.refresh(event, ["slots"])
                event.calc_popularity_sum()
                await session.commit()
                log.info(
                    f"    人気の和更新: {event.held_date} "
                    f"sum={event.popularity_sum} zone={event.zone}"
                )


# ─────────────────────────────────────────────
# ヘルパー
# ─────────────────────────────────────────────

def _slots_from_list(item: dict) -> list[dict]:
    """fetch_win5_listの結果からスロット情報を生成（詳細取得失敗時のフォールバック）"""
    slots = []
    for i, race_id in enumerate(item.get("race_ids", []), start=1):
        slots.append({"slot_number": i, "race_id": race_id,
                      "winner_horse_name": None, "winner_popularity": None})
    return slots


# netkeibaのrace_idに含まれる開催場コード
_VENUE_CODE = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟",
    "05": "東京", "06": "中山", "07": "中京", "08": "京都",
    "09": "阪神", "10": "小倉",
}

def _venue_from_race_id(race_id: str) -> str | None:
    # race_id = YYYYVVRRNN  V:会場(2桁) R:回(2桁) N:日(2桁) NN:レース(2桁)
    if len(race_id) == 12:
        return _VENUE_CODE.get(race_id[4:6])
    return None


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="WIN5データ収集パイプライン")
    parser.add_argument("--year",      type=int, action="append", dest="years",
                        metavar="YYYY", help="収集対象年（複数指定可）")
    parser.add_argument("--list-only", action="store_true",
                        help="WIN5開催一覧のみ収集（各レース結果は取得しない）")
    parser.add_argument("--force",     action="store_true",
                        help="既存データを上書き再取得")
    args = parser.parse_args()

    years = args.years or [date.today().year]
    for year in years:
        asyncio.run(collect_year(year, list_only=args.list_only, force=args.force))


if __name__ == "__main__":
    main()
