from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Puzzle(Base):
    __tablename__ = "puzzles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    puzzle_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    size: Mapped[int] = mapped_column(Integer)
    regions: Mapped[str] = mapped_column(Text)
    solution: Mapped[str] = mapped_column(Text)
    starter: Mapped[str] = mapped_column(Text, default="[]")
    difficulty: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    puzzle_id: Mapped[int] = mapped_column(ForeignKey("puzzles.id"))
    mode: Mapped[str] = mapped_column(String(16))
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hearts: Mapped[int] = mapped_column(Integer, default=3)
    hearts_lost: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    cats: Mapped[str] = mapped_column(Text, default="[]")
    marks: Mapped[str] = mapped_column(Text, default="[]")
    hints: Mapped[int] = mapped_column(Integer, default=0)
    history: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(16), default="playing")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
