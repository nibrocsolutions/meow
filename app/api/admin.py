"""Backup and restore. There is no password. Keep this on the home network."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Player, Puzzle, Run

router = APIRouter(prefix="/api/admin")


class ImportBody(BaseModel):
    players: list[dict] = Field(default_factory=list)
    puzzles: list[dict] = Field(default_factory=list)
    runs: list[dict] = Field(default_factory=list)


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    return {
        "players": db.query(Player).count(),
        "puzzles": db.query(Puzzle).count(),
        "runs": db.query(Run).count(),
    }


@router.get("/export")
def export_backup(db: Session = Depends(get_db)) -> dict:
    def row(item, fields: tuple[str, ...]) -> dict:
        payload = {}
        for field in fields:
            value = getattr(item, field)
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            payload[field] = value
        return payload

    return {
        "players": [row(item, ("id", "name", "created_at")) for item in db.query(Player).order_by(Player.id)],
        "puzzles": [
            row(
                item,
                ("id", "puzzle_key", "size", "regions", "solution", "starter", "difficulty", "created_at"),
            )
            for item in db.query(Puzzle).order_by(Puzzle.id)
        ],
        "runs": [
            row(
                item,
                (
                    "id",
                    "player_id",
                    "puzzle_id",
                    "mode",
                    "level",
                    "hearts",
                    "hearts_lost",
                    "elapsed_ms",
                    "cats",
                    "marks",
                    "hints",
                    "history",
                    "status",
                    "started_at",
                    "updated_at",
                    "finished_at",
                ),
            )
            for item in db.query(Run).order_by(Run.id)
        ],
    }


@router.post("/import")
def import_backup(body: ImportBody, db: Session = Depends(get_db)) -> dict:
    try:
        db.query(Run).delete()
        db.query(Puzzle).delete()
        db.query(Player).delete()
        for item in body.players:
            db.add(Player(id=int(item["id"]), name=str(item["name"])[:24]))
        for item in body.puzzles:
            db.add(
                Puzzle(
                    id=int(item["id"]),
                    puzzle_key=str(item["puzzle_key"])[:80],
                    size=int(item["size"]),
                    regions=_json_text(item["regions"]),
                    solution=_json_text(item["solution"]),
                    starter=_json_text(item.get("starter", "[]")),
                    difficulty=str(item["difficulty"])[:16],
                )
            )
        for item in body.runs:
            db.add(
                Run(
                    id=int(item["id"]),
                    player_id=int(item["player_id"]),
                    puzzle_id=int(item["puzzle_id"]),
                    mode=str(item["mode"])[:16],
                    level=item.get("level"),
                    hearts=int(item.get("hearts", 3)),
                    hearts_lost=int(item.get("hearts_lost", 0)),
                    elapsed_ms=int(item.get("elapsed_ms", 0)),
                    cats=_json_text(item.get("cats", "[]")),
                    marks=_json_text(item.get("marks", "[]")),
                    hints=int(item.get("hints", 0)),
                    history=_json_text(item.get("history", "[]")),
                    status=str(item.get("status", "playing"))[:16],
                )
            )
        db.commit()
    except (KeyError, TypeError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="That backup could not be read.") from exc
    return summary(db)


def _json_text(value) -> str:
    if isinstance(value, str):
        json.loads(value)
        return value
    return json.dumps(value)
