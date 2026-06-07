from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, UniqueConstraint
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
    __tablename__ = "races"

    id = Column(Integer, primary_key=True)
    race_id = Column(String, unique=True, nullable=False)  # 例: 202401010101
    held_date = Column(Date, nullable=False)
    venue = Column(String, nullable=False)
    race_number = Column(Integer, nullable=False)
    race_name = Column(String)
    course = Column(String)  # 芝/ダート
    distance = Column(Integer)

    entries = relationship("Entry", back_populates="race")
    win5_slot = relationship("Win5Slot", back_populates="race", uselist=False)

    __table_args__ = (UniqueConstraint("held_date", "venue", "race_number"),)


class Horse(Base):
    __tablename__ = "horses"

    id = Column(Integer, primary_key=True)
    horse_id = Column(String, unique=True, nullable=False)  # netkeibaの馬ID
    name = Column(String, nullable=False)
    sex = Column(String)
    birth_year = Column(Integer)

    entries = relationship("Entry", back_populates="horse")


class Entry(Base):
    __tablename__ = "entries"

    id = Column(Integer, primary_key=True)
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    horse_id = Column(Integer, ForeignKey("horses.id"), nullable=False)
    horse_number = Column(Integer)
    frame_number = Column(Integer)
    popularity = Column(Integer)   # 人気順位
    odds = Column(Float)
    finish_position = Column(Integer)  # 着順（nullは除外・競走中止等）

    race = relationship("Race", back_populates="entries")
    horse = relationship("Horse", back_populates="entries")

    __table_args__ = (UniqueConstraint("race_id", "horse_number"),)


class Win5Slot(Base):
    """WIN5対象レースと結果"""
    __tablename__ = "win5_slots"

    id = Column(Integer, primary_key=True)
    held_date = Column(Date, nullable=False)
    slot_number = Column(Integer, nullable=False)  # 1〜5
    race_id = Column(Integer, ForeignKey("races.id"), nullable=False)
    winner_horse_id = Column(Integer, ForeignKey("horses.id"))
    winner_popularity = Column(Integer)  # 勝ち馬の人気

    race = relationship("Race", back_populates="win5_slot")

    __table_args__ = (UniqueConstraint("held_date", "slot_number"),)


class Win5Result(Base):
    """WIN5開催ごとの集計結果"""
    __tablename__ = "win5_results"

    id = Column(Integer, primary_key=True)
    held_date = Column(Date, unique=True, nullable=False)
    popularity_sum = Column(Integer)   # 人気の和（5レース勝ち馬の合計）
    payout = Column(Integer)           # 払戻金（円）
    unit_count = Column(Integer)       # 的中口数

    @property
    def zone(self) -> str:
        """人気の和のゾーン分類"""
        if self.popularity_sum is None:
            return "unknown"
        s = self.popularity_sum
        if s <= 14:
            return "low"       # 低配当（避ける）
        elif s <= 22:
            return "target"    # ターゲットゾーン（15〜22）
        else:
            return "high"      # 超高配当（的中困難）


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
