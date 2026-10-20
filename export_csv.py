"""win5.db から export_events.csv / export_slots.csv を再生成する。

使い方:
  python export_csv.py

collect.py でデータを収集・更新した後、Supabaseへの取り込み用に
このスクリプトでCSVを作り直してからコミット・pushする。
"""
from __future__ import annotations

import csv

from sqlalchemy import select

from utils.db import SessionLocal, Win5Event, Win5Slot


def export_events(path: str = "export_events.csv") -> int:
    with SessionLocal() as session:
        events = session.execute(
            select(Win5Event).order_by(Win5Event.id)
        ).scalars().all()

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "event_date", "payout", "unit_count"])
            for e in events:
                writer.writerow([e.id, e.held_date.isoformat(), e.payout or "", e.unit_count or ""])

        return len(events)


def export_slots(path: str = "export_slots.csv") -> int:
    with SessionLocal() as session:
        slots = session.execute(
            select(Win5Slot).order_by(Win5Slot.id)
        ).scalars().all()

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["id", "event_id", "slot_number", "racecourse", "winner_horse_name", "winner_jockey", "winner_popularity"]
            )
            for s in slots:
                racecourse = s.race.venue if s.race else ""
                writer.writerow(
                    [
                        s.id,
                        s.event_id,
                        s.slot_number,
                        racecourse or "",
                        s.winner_horse_name or "",
                        s.winner_jockey or "",
                        s.winner_popularity if s.winner_popularity is not None else "",
                    ]
                )

        return len(slots)


def main():
    n_events = export_events()
    n_slots = export_slots()
    print(f"export_events.csv: {n_events} 行")
    print(f"export_slots.csv: {n_slots} 行")


if __name__ == "__main__":
    main()
