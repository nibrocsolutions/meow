"""Runs, hearts, and the home screen. The solution stays in the database."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from app.config import settings
from app.models import Player, Puzzle, Run, utcnow
from app.puzzle import (
    DAILY,
    ENDLESS,
    PuzzleError,
    campaign_profile,
    daily_seed,
    generate_puzzle,
    hint_for_player,
    rejection_reason,
)

MAX_HEARTS = 3
MAX_ELAPSED_MS = 24 * 60 * 60 * 1000
_puzzle_lock = threading.Lock()


class GameError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def clean_name(name: str) -> str:
    collapsed = " ".join(name.split())
    if not collapsed or len(collapsed) > 24:
        raise GameError("Use a name of 1 to 24 characters.")
    return collapsed


def list_players(db: Session) -> list[dict]:
    rows = db.query(Player).order_by(Player.created_at, Player.id).all()
    return [{"id": row.id, "name": row.name} for row in rows]


def create_player(db: Session, name: str) -> dict:
    player = Player(name=clean_name(name))
    db.add(player)
    db.commit()
    db.refresh(player)
    return {"id": player.id, "name": player.name}


def rename_player(db: Session, player_id: int, name: str) -> dict:
    player = _player(db, player_id)
    player.name = clean_name(name)
    db.commit()
    return {"id": player.id, "name": player.name}


def delete_player(db: Session, player_id: int) -> None:
    player = _player(db, player_id)
    db.query(Run).filter(Run.player_id == player.id).delete()
    db.delete(player)
    db.commit()


def home_payload(db: Session, player_id: int) -> dict:
    player = _player(db, player_id)
    today = _today()
    won_levels = {
        level
        for (level,) in db.query(Run.level)
        .filter(Run.player_id == player.id, Run.mode == "campaign", Run.status == "won", Run.level.isnot(None))
        .all()
    }
    next_level = 1
    while next_level in won_levels:
        next_level += 1
    playing_rows = (
        db.query(Run, Puzzle)
        .join(Puzzle, Puzzle.id == Run.puzzle_id)
        .filter(Run.player_id == player.id, Run.status == "playing")
        .order_by(Run.updated_at.desc())
        .all()
    )
    playing = [
        {
            "run_id": run.id,
            "mode": run.mode,
            "level": run.level,
            "difficulty": puzzle.difficulty,
            "title": _title(run, puzzle),
            "elapsed_ms": run.elapsed_ms,
        }
        for run, puzzle in playing_rows[:8]
    ]
    limit = max(18, next_level + 11)
    levels = []
    for level in range(1, limit + 1):
        profile = campaign_profile(level)
        state = "locked"
        if level < next_level:
            state = "won"
        elif level == next_level:
            state = "open"
        active = next(
            (item for item in playing if item["mode"] == "campaign" and item["level"] == level),
            None,
        )
        if active:
            state = "playing"
        best = (
            db.query(func.min(Run.elapsed_ms))
            .filter(
                Run.player_id == player.id,
                Run.mode == "campaign",
                Run.level == level,
                Run.status == "won",
            )
            .scalar()
        )
        levels.append(
            {
                "level": level,
                "size": profile["size"],
                "tier": profile["tier"],
                "status": state,
                "best_ms": best,
                "run_id": active["run_id"] if active else None,
            }
        )
    daily = []
    for difficulty, profile in DAILY.items():
        puzzle = db.query(Puzzle).filter(Puzzle.puzzle_key == _daily_key(today, difficulty)).one_or_none()
        run = None
        if puzzle is not None:
            run = (
                db.query(Run)
                .filter(Run.player_id == player.id, Run.puzzle_id == puzzle.id)
                .order_by(Run.id.desc())
                .first()
            )
        best = None
        if puzzle is not None:
            best = (
                db.query(func.min(Run.elapsed_ms))
                .filter(Run.player_id == player.id, Run.puzzle_id == puzzle.id, Run.status == "won")
                .scalar()
            )
        daily.append(
            {
                "difficulty": difficulty,
                "tier": profile["tier"],
                "size": profile["size"],
                "status": run.status if run else "new",
                "run_id": run.id if run else None,
                "best_ms": best,
            }
        )
    return {
        "player": {"id": player.id, "name": player.name},
        "today": today.isoformat(),
        "campaign_next": next_level,
        "campaign_completed": len(won_levels),
        "playing": playing,
        "daily": daily,
        "streak": _streak(db, player.id, today),
        "levels": levels,
        "stats": _stats(db, player.id),
    }


def start_run(
    db: Session,
    player_id: int,
    mode: str,
    level: int | None = None,
    difficulty: str | None = None,
    replay: bool = False,
) -> dict:
    player = _player(db, player_id)
    if mode == "campaign":
        return _start_campaign(db, player, level, replay)
    if mode == "daily":
        return _start_daily(db, player, difficulty, replay)
    if mode == "endless":
        return _start_endless(db, player, difficulty, replay)
    raise GameError("Unknown game.")


def get_run(db: Session, run_id: int, player_id: int) -> dict:
    run, puzzle = _own(db, run_id, player_id)
    return _public(db, run, puzzle)


def tap(db: Session, run_id: int, player_id: int, row: int, col: int, elapsed_ms: int | None) -> dict:
    run, puzzle = _own(db, run_id, player_id)
    if run.status != "playing":
        return _public(db, run, puzzle)
    _bounds(puzzle.size, row, col)
    _clock(run, elapsed_ms)
    starters = _pairs(puzzle.starter)
    cats = _pairs(run.cats)
    marks = _pairs(run.marks)
    cell = (row, col)
    if cell in starters:
        db.commit()
        return _public(db, run, puzzle)
    _push(run)
    lost_heart = False
    message = None
    if cell in cats:
        cats = [item for item in cats if tuple(item) != cell]
    elif cell in marks:
        solution = _solution_cells(puzzle)
        if cell in solution:
            marks = [item for item in marks if tuple(item) != cell]
            cats.append(cell)
        else:
            lost_heart = True
            occupied = set(starters) | {tuple(item) for item in cats}
            message = rejection_reason(puzzle.size, json.loads(puzzle.regions), occupied, row, col)
            run.hearts = max(0, run.hearts - 1)
            run.hearts_lost += 1
            if run.hearts == 0:
                run.status = "lost"
                run.finished_at = utcnow()
    else:
        marks.append((row, col))
    run.cats = _dump_pairs(cats)
    run.marks = _dump_pairs(marks)
    just_won = False
    if run.status == "playing" and _solved(puzzle, cats):
        run.status = "won"
        run.finished_at = utcnow()
        just_won = True
    run.updated_at = utcnow()
    db.commit()
    extra: dict = {}
    if lost_heart:
        extra["lost_heart"] = True
        extra["message"] = message
    if just_won:
        extra.update(_best(db, run, puzzle))
    return _public(db, run, puzzle, extra)


def add_marks(
    db: Session,
    run_id: int,
    player_id: int,
    cells: list[list[int]],
    elapsed_ms: int | None,
) -> dict:
    run, puzzle = _own(db, run_id, player_id)
    if run.status != "playing":
        return _public(db, run, puzzle)
    _clock(run, elapsed_ms)
    if len(cells) > puzzle.size * puzzle.size:
        raise GameError("Too many cells.")
    starters = set(_pairs(puzzle.starter))
    cats = set(_pairs(run.cats))
    marks = _pairs(run.marks)
    seen = set(marks)
    added = False
    for item in cells:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise GameError("Each cell needs a row and a column.")
        row, col = item
        if not isinstance(row, int) or not isinstance(col, int):
            raise GameError("Each cell needs a row and a column.")
        _bounds(puzzle.size, row, col)
        cell = (row, col)
        if cell in starters or cell in cats or cell in seen:
            continue
        marks.append(cell)
        seen.add(cell)
        added = True
    if not added:
        db.commit()
        return _public(db, run, puzzle)
    _push_before_marks(run, marks)
    run.updated_at = utcnow()
    db.commit()
    return _public(db, run, puzzle)


def undo(db: Session, run_id: int, player_id: int) -> dict:
    run, puzzle = _own(db, run_id, player_id)
    history = json.loads(run.history or "[]")
    if not history:
        return _public(db, run, puzzle)
    snap = history.pop()
    run.history = json.dumps(history)
    run.cats = json.dumps(snap["cats"])
    run.marks = json.dumps(snap["marks"])
    run.hearts = snap["hearts"]
    run.hearts_lost = snap["hearts_lost"]
    run.hints = snap["hints"]
    run.status = snap["status"]
    run.elapsed_ms = snap["elapsed_ms"]
    run.finished_at = None if run.status == "playing" else run.finished_at
    run.updated_at = utcnow()
    db.commit()
    return _public(db, run, puzzle)


def restart(db: Session, run_id: int, player_id: int) -> dict:
    run, puzzle = _own(db, run_id, player_id)
    if run.status == "won":
        raise GameError("This one is already solved. Open it again to play a fresh copy.")
    run.hearts = MAX_HEARTS
    run.elapsed_ms = 0
    run.cats = "[]"
    run.marks = "[]"
    run.hints = 0
    run.history = "[]"
    run.status = "playing"
    run.finished_at = None
    run.updated_at = utcnow()
    db.commit()
    return _public(db, run, puzzle)


def give_hint(db: Session, run_id: int, player_id: int, elapsed_ms: int | None) -> dict:
    run, puzzle = _own(db, run_id, player_id)
    if run.status != "playing":
        return _public(db, run, puzzle)
    _clock(run, elapsed_ms)
    regions = json.loads(puzzle.regions)
    starters = _pairs(puzzle.starter)
    cats = _pairs(run.cats)
    marks = _pairs(run.marks)
    placed = set(starters) | set(cats)
    step = hint_for_player(puzzle.size, regions, placed, set(marks))
    if step is None:
        db.commit()
        return _public(db, run, puzzle, {"hint": "Nothing further is forced. Look again, or undo a mark."})
    solution = _solution_cells(puzzle)
    changed = False
    if step.kind == "cat":
        row, col = step.cells[0]
        if (row, col) in solution and (row, col) not in placed:
            _push(run)
            marks = [item for item in marks if tuple(item) != (row, col)]
            cats.append((row, col))
            changed = True
    else:
        seen = set(marks)
        fresh = []
        for row, col in step.cells:
            if (row, col) in solution or (row, col) in placed or (row, col) in seen:
                continue
            fresh.append((row, col))
        if fresh:
            _push(run)
            marks.extend(fresh)
            changed = True
    if not changed:
        db.commit()
        return _public(db, run, puzzle, {"hint": "Nothing further is forced. Look again, or undo a mark."})
    run.hints += 1
    run.cats = _dump_pairs(cats)
    run.marks = _dump_pairs(marks)
    just_won = False
    if _solved(puzzle, cats):
        run.status = "won"
        run.finished_at = utcnow()
        just_won = True
    run.updated_at = utcnow()
    db.commit()
    extra = {"hint": step.text}
    if just_won:
        extra.update(_best(db, run, puzzle))
    return _public(db, run, puzzle, extra)


def set_clock(db: Session, run_id: int, player_id: int, elapsed_ms: int) -> dict:
    run, puzzle = _own(db, run_id, player_id)
    if run.status == "playing":
        _clock(run, elapsed_ms)
        run.updated_at = utcnow()
        db.commit()
    return {"id": run.id, "elapsed_ms": run.elapsed_ms, "status": run.status}


def _start_campaign(db: Session, player: Player, level: int | None, replay: bool) -> dict:
    won_levels = {
        row
        for (row,) in db.query(Run.level)
        .filter(Run.player_id == player.id, Run.mode == "campaign", Run.status == "won")
        .all()
    }
    next_level = 1
    while next_level in won_levels:
        next_level += 1
    if level is None:
        level = next_level
    if level < 1:
        raise GameError("That level doesn't exist.")
    if level > next_level:
        raise GameError("Finish the earlier levels first.")
    profile = campaign_profile(level)
    puzzle = _get_or_create(
        db,
        key=f"campaign:{level}",
        size=profile["size"],
        seed=profile["seed"],
        starter=profile["starter"],
        difficulty=profile["tier"].lower(),
    )
    return _resume_or_create(db, player, puzzle, "campaign", level, replay)


def _start_daily(db: Session, player: Player, difficulty: str | None, replay: bool) -> dict:
    if difficulty not in DAILY:
        raise GameError("Pick an easy, normal, or hard daily.")
    today = _today()
    profile = DAILY[difficulty]
    puzzle = _get_or_create(
        db,
        key=_daily_key(today, difficulty),
        size=profile["size"],
        seed=daily_seed(today.isoformat(), difficulty),
        starter=profile["starter"],
        difficulty=difficulty,
    )
    return _resume_or_create(db, player, puzzle, "daily", None, replay)


def _start_endless(db: Session, player: Player, difficulty: str | None, replay: bool) -> dict:
    if difficulty not in ENDLESS:
        raise GameError("Pick easy, normal, hard, or expert.")
    if not replay:
        existing = (
            db.query(Run, Puzzle)
            .join(Puzzle, Puzzle.id == Run.puzzle_id)
            .filter(
                Run.player_id == player.id,
                Run.mode == "endless",
                Run.status == "playing",
                Puzzle.difficulty == difficulty,
            )
            .order_by(Run.id.desc())
            .first()
        )
        if existing:
            run, puzzle = existing
            return _public(db, run, puzzle)
    profile = ENDLESS[difficulty]
    puzzle = _get_or_create(
        db,
        key=f"endless:{uuid.uuid4().hex}",
        size=profile["size"],
        seed=uuid.uuid4().int & 0x7FFFFFFF,
        starter=profile["starter"],
        difficulty=difficulty,
    )
    return _new_run(db, player, puzzle, "endless", None)


def _resume_or_create(
    db: Session,
    player: Player,
    puzzle: Puzzle,
    mode: str,
    level: int | None,
    replay: bool,
) -> dict:
    existing = (
        db.query(Run)
        .filter(Run.player_id == player.id, Run.puzzle_id == puzzle.id, Run.mode == mode)
        .order_by(Run.id.desc())
        .first()
    )
    if existing and existing.status == "playing":
        return _public(db, existing, puzzle)
    if existing and not replay:
        return _public(db, existing, puzzle)
    return _new_run(db, player, puzzle, mode, level)


def _new_run(db: Session, player: Player, puzzle: Puzzle, mode: str, level: int | None) -> dict:
    run = Run(
        player_id=player.id,
        puzzle_id=puzzle.id,
        mode=mode,
        level=level,
        hearts=MAX_HEARTS,
        hearts_lost=0,
        elapsed_ms=0,
        cats="[]",
        marks="[]",
        hints=0,
        history="[]",
        status="playing",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return _public(db, run, puzzle)


def _get_or_create(
    db: Session,
    key: str,
    size: int,
    seed: int,
    starter: bool,
    difficulty: str,
) -> Puzzle:
    existing = db.query(Puzzle).filter(Puzzle.puzzle_key == key).one_or_none()
    if existing:
        return existing
    with _puzzle_lock:
        existing = db.query(Puzzle).filter(Puzzle.puzzle_key == key).one_or_none()
        if existing:
            return existing
        try:
            generated = generate_puzzle(size, seed, starter)
        except PuzzleError as exc:
            raise GameError("Couldn't build a fair puzzle. Try again.", 503) from exc
        row = Puzzle(
            puzzle_key=key,
            size=generated.size,
            regions=json.dumps(list(generated.regions)),
            solution=json.dumps(list(generated.solution)),
            starter=json.dumps([list(cell) for cell in generated.starters]),
            difficulty=difficulty,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            row = db.query(Puzzle).filter(Puzzle.puzzle_key == key).one()
        else:
            db.refresh(row)
        return row


def _public(db: Session, run: Run, puzzle: Puzzle, extra: dict | None = None) -> dict:
    cats = json.loads(run.cats or "[]")
    marks = json.loads(run.marks or "[]")
    starters = json.loads(puzzle.starter or "[]")
    payload = {
        "id": run.id,
        "mode": run.mode,
        "level": run.level,
        "title": _title(run, puzzle),
        "difficulty": puzzle.difficulty,
        "status": run.status,
        "hearts": run.hearts,
        "max_hearts": MAX_HEARTS,
        "elapsed_ms": run.elapsed_ms,
        "hints": run.hints,
        "size": puzzle.size,
        "regions": json.loads(puzzle.regions),
        "cats": cats,
        "marks": marks,
        "starters": starters,
        "placed": len(cats) + len(starters),
        "needed": puzzle.size,
        "can_undo": bool(json.loads(run.history or "[]")),
    }
    if extra:
        payload.update(extra)
    if run.status == "won" and "is_best" not in payload:
        payload.update(_best(db, run, puzzle))
    return payload


def _best(db: Session, run: Run, puzzle: Puzzle) -> dict:
    query = db.query(func.min(Run.elapsed_ms)).filter(
        Run.player_id == run.player_id,
        Run.status == "won",
    )
    if run.mode == "campaign":
        query = query.filter(Run.mode == "campaign", Run.level == run.level)
    elif run.mode == "daily":
        query = query.filter(Run.puzzle_id == puzzle.id)
    else:
        query = query.filter(Run.mode == "endless", Run.puzzle_id.in_(
            db.query(Puzzle.id).filter(Puzzle.difficulty == puzzle.difficulty)
        ))
    best = query.scalar()
    return {"best_ms": best, "is_best": best == run.elapsed_ms}


def _stats(db: Session, player_id: int) -> dict:
    solved = db.query(func.count(Run.id)).filter(Run.player_id == player_id, Run.status == "won").scalar() or 0
    hints = db.query(func.coalesce(func.sum(Run.hints), 0)).filter(Run.player_id == player_id).scalar() or 0
    hearts = (
        db.query(func.coalesce(func.sum(Run.hearts_lost), 0)).filter(Run.player_id == player_id).scalar() or 0
    )
    bests = {}
    for difficulty in ("cozy", "easy", "normal", "hard", "expert"):
        best = (
            db.query(func.min(Run.elapsed_ms))
            .join(Puzzle, Puzzle.id == Run.puzzle_id)
            .filter(Run.player_id == player_id, Run.status == "won", Puzzle.difficulty == difficulty)
            .scalar()
        )
        bests[difficulty] = best
    return {"solved": solved, "hints": int(hints), "hearts_lost": int(hearts), "best": bests}


def _streak(db: Session, player_id: int, today: date) -> int:
    rows = (
        db.query(Puzzle.puzzle_key)
        .join(Run, Run.puzzle_id == Puzzle.id)
        .filter(Run.player_id == player_id, Run.mode == "daily", Run.status == "won")
        .all()
    )
    won_days = set()
    for (key,) in rows:
        parts = key.split(":")
        if len(parts) >= 2:
            won_days.add(parts[1])
    cursor = today
    if cursor.isoformat() not in won_days:
        cursor = today - timedelta(days=1)
    streak = 0
    while cursor.isoformat() in won_days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _today() -> date:
    try:
        zone = ZoneInfo(settings.daily_tz)
    except Exception as exc:
        raise GameError("The daily clock is misconfigured.", 500) from exc
    return datetime.now(zone).date()


def _daily_key(day: date, difficulty: str) -> str:
    return f"daily:{day.isoformat()}:{difficulty}"


def _title(run: Run, puzzle: Puzzle) -> str:
    if run.mode == "campaign" and run.level:
        return f"Level {run.level}"
    if run.mode == "daily":
        return f"Daily · {puzzle.difficulty}"
    return puzzle.difficulty.capitalize()


def _player(db: Session, player_id: int) -> Player:
    player = db.get(Player, player_id)
    if player is None:
        raise GameError("That player is not on this Pi.", 404)
    return player


def _own(db: Session, run_id: int, player_id: int) -> tuple[Run, Puzzle]:
    _player(db, player_id)
    run = db.get(Run, run_id)
    if run is None or run.player_id != player_id:
        raise GameError("That puzzle is not on this phone.", 404)
    puzzle = db.get(Puzzle, run.puzzle_id)
    if puzzle is None:
        raise GameError("That puzzle is missing.", 404)
    return run, puzzle


def _pairs(text: str) -> list[tuple[int, int]]:
    return [(int(row), int(col)) for row, col in json.loads(text or "[]")]


def _solution_cells(puzzle: Puzzle) -> set[tuple[int, int]]:
    return {(row, int(col)) for row, col in enumerate(json.loads(puzzle.solution))}


def _solved(puzzle: Puzzle, cats: list[tuple[int, int]]) -> bool:
    have = set(_pairs(puzzle.starter)) | {(int(row), int(col)) for row, col in cats}
    return have == _solution_cells(puzzle)


def _dump_pairs(cells: list[tuple[int, int]]) -> str:
    return json.dumps([[int(row), int(col)] for row, col in cells])


def _bounds(size: int, row: int, col: int) -> None:
    if row < 0 or col < 0 or row >= size or col >= size:
        raise GameError("That cell is off the board.")


def _clock(run: Run, elapsed_ms: int | None) -> None:
    if elapsed_ms is None or run.status != "playing":
        return
    if not isinstance(elapsed_ms, int):
        raise GameError("The timer needs a whole number of milliseconds.")
    run.elapsed_ms = max(0, min(elapsed_ms, MAX_ELAPSED_MS))


def _snapshot(run: Run) -> dict:
    return {
        "cats": json.loads(run.cats or "[]"),
        "marks": json.loads(run.marks or "[]"),
        "hearts": run.hearts,
        "hearts_lost": run.hearts_lost,
        "hints": run.hints,
        "status": run.status,
        "elapsed_ms": run.elapsed_ms,
    }


def _push(run: Run) -> None:
    history = json.loads(run.history or "[]")
    history.append(_snapshot(run))
    run.history = json.dumps(history[-80:])


def _push_before_marks(run: Run, marks: list[tuple[int, int]]) -> None:
    """History must describe the board from before the drag."""
    history = json.loads(run.history or "[]")
    history.append(_snapshot(run))
    run.history = json.dumps(history[-80:])
    run.marks = _dump_pairs(marks)
