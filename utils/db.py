from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Date, ForeignKey,
    UniqueConstraint, CheckConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker, Session
import os
from dotenv import load_dotenv

load_dotenv()

# 同期版SQLite（aiosqlite不要・greenlet不要）
DATABASE_URL = os.getenv("DATABASE_URL_SYNC", "sqlite:///./win5.db")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Race(Base):
    __tablename__ = "races"

    id          = Column(Integer, primary_key=True)
    race_id     = Column(String(12), unique=True, nullable=False)
    held_date   = Column(Date, nullable=False)
    venue       = Column(String(10))
    race_number = Column(Integer)
    race_name   = Column(String(100))
    course      = Column(String(4))
    distance    = Column(Integer)

    entries   = relationship("Entry",    back_populates="race", cascade="all, delete-orphan")
    win5_slot = relationship("Win5Slot", back_populates="race", uselist=False)

    __table_args__ = (UniqueConstraint("held_date", "venue", "race_number"),)


class Horse(Base):
    __tablename__ = "horses"

    id         = Column(Integer, primary_key=True)
    horse_id   = Column(String(20), unique=True, nullable=False)
    name       = Column(String(50), nullable=False)
    sex        = Column(String(4))
    birth_year = Column(Integer)

    entries = relationship("Entry", back_populates="horse")


class Entry(Base):
    __tablename__ = "entries"

    id               = Column(Integer, primary_key=True)
    race_id          = Column(Integer, ForeignKey("races.id"),  nullable=False)
    horse_id         = Column(Integer, ForeignKey("horses.id"), nullable=False)
    horse_number     = Column(Integer)
    frame_number     = Column(Integer)
    popularity       = Column(Integer)
    odds             = Column(Float)
    finish_position  = Column(Integer)

    race  = relationship("Race",  back_populates="entries")
    horse = relationship("Horse", back_populates="entries")

    __table_args__ = (UniqueConstraint("race_id", "horse_number"),)


class Win5Event(Base):
    __tablename__ = "win5_events"

    id             = Column(Integer, primary_key=True)
    held_date      = Column(Date, unique=True, nullable=False)
    payout         = Column(Integer)
    unit_count     = Column(Integer)
    popularity_sum = Column(Integer)

    slots = relationship("Win5Slot", back_populates="event",
                         order_by="Win5Slot.slot_number",
                         cascade="all, delete-orphan")

    @property
    def zone(self) -> str:
        if self.popularity_sum is None:
            return "unknown"
        s = self.popularity_sum
        if s <= 14:
            return "low"
        elif s <= 22:
            return "target"
        else:
            return "high"

    def calc_popularity_sum(self):
        pops = [s.winner_popularity for s in self.slots if s.winner_popularity is not None]
        self.popularity_sum = sum(pops) if len(pops) == 5 else None


class Win5Slot(Base):
    __tablename__ = "win5_slots"

    id                 = Column(Integer, primary_key=True)
    event_id           = Column(Integer, ForeignKey("win5_events.id"), nullable=False)
    slot_number        = Column(Integer, nullable=False)
    race_id            = Column(Integer, ForeignKey("races.id"), nullable=True)
    race_id_str        = Column(String(12))
    winner_horse_id    = Column(Integer, ForeignKey("horses.id"), nullable=True)
    winner_horse_name  = Column(String(50))
    winner_popularity  = Column(Integer)

    event = relationship("Win5Event", back_populates="slots")
    race  = relationship("Race",  back_populates="win5_slot", foreign_keys=[race_id])
    horse = relationship("Horse", foreign_keys=[winner_horse_id])

    __table_args__ = (
        UniqueConstraint("event_id", "slot_number"),
        CheckConstraint("slot_number BETWEEN 1 AND 5"),
    )


def init_db():
    Base.metadata.create_all(engine)
