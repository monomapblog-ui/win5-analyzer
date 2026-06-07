from sqlalchemy import (
    Column, Integer, String, Float, Date, ForeignKey,
    UniqueConstraint, CheckConstraint, event,
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./win5.db")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Race(Base):
    """競馬レース（WIN5対象外も含む）"""
    __tablename__ = "races"

    id          = Column(Integer, primary_key=True)
    race_id     = Column(String(12), unique=True, nullable=False)  # 202401010101
    held_date   = Column(Date, nullable=False)
    venue       = Column(String(10))          # 東京・中山など
    race_number = Column(Integer)
    race_name   = Column(String(100))
    course      = Column(String(4))           # 芝 / ダート
    distance    = Column(Integer)

    entries   = relationship("Entry",    back_populates="race", cascade="all, delete-orphan")
    win5_slot = relationship("Win5Slot", back_populates="race", uselist=False)

    __table_args__ = (
        UniqueConstraint("held_date", "venue", "race_number"),
    )


class Horse(Base):
    """競走馬マスタ"""
    __tablename__ = "horses"

    id         = Column(Integer, primary_key=True)
    horse_id   = Column(String(20), unique=True, nullable=False)  # netkeibaの馬ID
    name       = Column(String(50), nullable=False)
    sex        = Column(String(4))
    birth_year = Column(Integer)

    entries = relationship("Entry", back_populates="horse")


class Entry(Base):
    """レースへの出走情報（1頭1行）"""
    __tablename__ = "entries"

    id               = Column(Integer, primary_key=True)
    race_id          = Column(Integer, ForeignKey("races.id"),  nullable=False)
    horse_id         = Column(Integer, ForeignKey("horses.id"), nullable=False)
    horse_number     = Column(Integer)
    frame_number     = Column(Integer)
    popularity       = Column(Integer)     # 人気順位
    odds             = Column(Float)
    finish_position  = Column(Integer)     # 着順（除外・競走中止はNULL）

    race  = relationship("Race",  back_populates="entries")
    horse = relationship("Horse", back_populates="entries")

    __table_args__ = (UniqueConstraint("race_id", "horse_number"),)


class Win5Event(Base):
    """WIN5開催（1日1行）"""
    __tablename__ = "win5_events"

    id             = Column(Integer, primary_key=True)
    held_date      = Column(Date, unique=True, nullable=False)
    payout         = Column(Integer)        # 払戻金（円）、不的中はNULL
    unit_count     = Column(Integer)        # 的中口数
    popularity_sum = Column(Integer)        # 人気の和（5レース勝ち馬の合計）

    slots = relationship("Win5Slot", back_populates="event",
                         order_by="Win5Slot.slot_number",
                         cascade="all, delete-orphan")

    @property
    def zone(self) -> str:
        """
        人気の和ゾーン分類:
          low    : 〜14  （低配当・避ける）
          target : 15〜22 （ターゲット・高配当）
          high   : 23〜   （超高配当・的中困難）
        """
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
        """スロットの勝ち馬人気を合計してpopularity_sumを更新する"""
        pops = [s.winner_popularity for s in self.slots if s.winner_popularity is not None]
        self.popularity_sum = sum(pops) if len(pops) == 5 else None


class Win5Slot(Base):
    """WIN5対象の個別レース（1開催につき5行）"""
    __tablename__ = "win5_slots"

    id                 = Column(Integer, primary_key=True)
    event_id           = Column(Integer, ForeignKey("win5_events.id"), nullable=False)
    slot_number        = Column(Integer, nullable=False)   # 1〜5
    race_id            = Column(Integer, ForeignKey("races.id"), nullable=True)
    race_id_str        = Column(String(12))                # 収集前はrace_idがNULLなので文字列を保持
    winner_horse_id    = Column(Integer, ForeignKey("horses.id"), nullable=True)
    winner_horse_name  = Column(String(50))
    winner_popularity  = Column(Integer)                   # 勝ち馬の人気

    event = relationship("Win5Event", back_populates="slots")
    race  = relationship("Race",  back_populates="win5_slot", foreign_keys=[race_id])
    horse = relationship("Horse", foreign_keys=[winner_horse_id])

    __table_args__ = (
        UniqueConstraint("event_id", "slot_number"),
        CheckConstraint("slot_number BETWEEN 1 AND 5"),
    )


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
