from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.game import (
    GameError,
    add_marks,
    create_player,
    delete_player,
    get_run,
    give_hint,
    home_payload,
    list_players,
    rename_player,
    restart,
    set_clock,
    start_run,
    tap,
    undo,
)

router = APIRouter(prefix="/api")


class PlayerBody(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class StartBody(BaseModel):
    player_id: int
    mode: str
    level: int | None = None
    difficulty: str | None = None
    replay: bool = False


class TapBody(BaseModel):
    player_id: int
    row: int
    col: int
    elapsed_ms: int | None = None


class MarksBody(BaseModel):
    player_id: int
    cells: list[list[int]]
    elapsed_ms: int | None = None


class ClockBody(BaseModel):
    player_id: int
    elapsed_ms: int = Field(ge=0)


class RunBody(BaseModel):
    player_id: int
    elapsed_ms: int | None = None


def _call(action):
    try:
        return action()
    except GameError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc


@router.get("/health")
def health() -> dict:
    return {"ok": True, "app": "Meow"}


@router.get("/players")
def get_players(db: Session = Depends(get_db)) -> list[dict]:
    return list_players(db)


@router.post("/players")
def post_player(body: PlayerBody, db: Session = Depends(get_db)) -> dict:
    return _call(lambda: create_player(db, body.name))


@router.patch("/players/{player_id}")
def patch_player(player_id: int, body: PlayerBody, db: Session = Depends(get_db)) -> dict:
    return _call(lambda: rename_player(db, player_id, body.name))


@router.delete("/players/{player_id}")
def remove_player(player_id: int, db: Session = Depends(get_db)) -> dict:
    _call(lambda: delete_player(db, player_id))
    return {"ok": True}


@router.get("/home")
def get_home(player_id: int, db: Session = Depends(get_db)) -> dict:
    return _call(lambda: home_payload(db, player_id))


@router.post("/runs")
def post_run(body: StartBody, db: Session = Depends(get_db)) -> dict:
    return _call(
        lambda: start_run(
            db,
            body.player_id,
            body.mode,
            level=body.level,
            difficulty=body.difficulty,
            replay=body.replay,
        )
    )


@router.get("/runs/{run_id}")
def read_run(run_id: int, player_id: int, db: Session = Depends(get_db)) -> dict:
    return _call(lambda: get_run(db, run_id, player_id))


@router.post("/runs/{run_id}/tap")
def post_tap(run_id: int, body: TapBody, db: Session = Depends(get_db)) -> dict:
    return _call(lambda: tap(db, run_id, body.player_id, body.row, body.col, body.elapsed_ms))


@router.post("/runs/{run_id}/marks")
def post_marks(run_id: int, body: MarksBody, db: Session = Depends(get_db)) -> dict:
    return _call(lambda: add_marks(db, run_id, body.player_id, body.cells, body.elapsed_ms))


@router.post("/runs/{run_id}/undo")
def post_undo(run_id: int, body: RunBody, db: Session = Depends(get_db)) -> dict:
    return _call(lambda: undo(db, run_id, body.player_id))


@router.post("/runs/{run_id}/restart")
def post_restart(run_id: int, body: RunBody, db: Session = Depends(get_db)) -> dict:
    return _call(lambda: restart(db, run_id, body.player_id))


@router.post("/runs/{run_id}/hint")
def post_hint(run_id: int, body: RunBody, db: Session = Depends(get_db)) -> dict:
    return _call(lambda: give_hint(db, run_id, body.player_id, body.elapsed_ms))


@router.post("/runs/{run_id}/clock")
def post_clock(run_id: int, body: ClockBody, db: Session = Depends(get_db)) -> dict:
    return _call(lambda: set_clock(db, run_id, body.player_id, body.elapsed_ms))
