from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Date, DateTime, ForeignKey,
    UniqueConstraint, CheckConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker, Session
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Render.com は DATABASE_URL_SYNC に postgresql:// を渡してくるため psycopg2 用に変換
DATABASE_URL = os.getenv("DATABASE_URL_SYNC", "sqlite:///./win5.db")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

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


class Win5RaceFeature(Base):
    """WIN5各スロットのレース特徴量（難易度分析用）"""
    __tablename__ = "win5_race_features"

    id              = Column(Integer, primary_key=True)
    slot_id         = Column(Integer, ForeignKey("win5_slots.id"), unique=True, nullable=False)
    field_size      = Column(Integer)    # 出走頭数
    course_type     = Column(String(4))  # 芝 / ダート / 障害
    distance        = Column(Integer)    # 距離(m)
    track_condition = Column(String(6))  # 良 / 稍重 / 重 / 不良
    fav1_odds       = Column(Float)      # 1番人気単勝オッズ
    fav2_odds       = Column(Float)      # 2番人気単勝オッズ
    winner_odds     = Column(Float)      # 勝ち馬オッズ
    winner_pop      = Column(Integer)    # 勝ち馬人気（再確認用）

    slot = relationship("Win5Slot", backref="feature")


class OddsSnapshot(Base):
    """オッズのスナップショット（時刻別に保存して変動を追跡）"""
    __tablename__ = "odds_snapshots"

    id            = Column(Integer, primary_key=True)
    race_id       = Column(String(12), nullable=False)
    horse_number  = Column(Integer,    nullable=False)
    horse_name    = Column(String(50))
    odds          = Column(Float)
    popularity    = Column(Integer)
    snapshot_at   = Column(DateTime, default=datetime.now, nullable=False)
    label         = Column(String(20))  # "前日夜" / "当日朝" / "締切前" など

    __table_args__ = (UniqueConstraint("race_id", "horse_number", "snapshot_at"),)


def init_db():
    Base.metadata.create_all(engine)
