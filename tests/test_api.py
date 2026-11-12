import json

from app.database import SessionLocal
from app.models import Puzzle


def _player(client, name="Ada"):
    response = client.post("/api/players", json={"name": name})
    assert response.status_code == 200
    return response.json()


def _solution(puzzle_id):
    db = SessionLocal()
    try:
        puzzle = db.get(Puzzle, puzzle_id)
        columns = json.loads(puzzle.solution)
        starters = {tuple(cell) for cell in json.loads(puzzle.starter)}
        return [(row, col) for row, col in enumerate(columns) if (row, col) not in starters]
    finally:
        db.close()


def _puzzle_id(run_id):
    db = SessionLocal()
    try:
        from app.models import Run

        return db.get(Run, run_id).puzzle_id
    finally:
        db.close()


def test_health_and_page(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
    page = client.get("/")
    assert page.status_code == 200
    assert "Meow" in page.text
    assert "/static/js/app.js?v=" in page.text


def test_campaign_play_hearts_hint_and_win(client):
    player = _player(client)
    empty = client.post("/api/players", json={"name": "   "})
    assert empty.status_code == 400

    skipped = client.post("/api/runs", json={"player_id": player["id"], "mode": "campaign", "level": 5})
    assert skipped.status_code == 400

    started = client.post("/api/runs", json={"player_id": player["id"], "mode": "campaign", "level": 1})
    assert started.status_code == 200
    run = started.json()
    assert "solution" not in run
    assert run["size"] == 5
    assert run["starters"]
    assert run["hearts"] == 3
    assert len(run["regions"]) == 25

    again = client.post("/api/runs", json={"player_id": player["id"], "mode": "campaign", "level": 1})
    assert again.json()["id"] == run["id"]

    other = _player(client, "Bea")
    hidden = client.get(f"/api/runs/{run['id']}?player_id={other['id']}")
    assert hidden.status_code == 404

    starter = tuple(run["starters"][0])
    wrong = next(
        (row, col)
        for row in range(run["size"])
        for col in range(run["size"])
        if (row, col) != starter and row == starter[0]
    )
    marked = client.post(
        f"/api/runs/{run['id']}/tap",
        json={"player_id": player["id"], "row": wrong[0], "col": wrong[1], "elapsed_ms": 1000},
    )
    assert marked.status_code == 200
    assert marked.json()["marks"] == [[wrong[0], wrong[1]]]
    missed = client.post(
        f"/api/runs/{run['id']}/tap",
        json={"player_id": player["id"], "row": wrong[0], "col": wrong[1], "elapsed_ms": 1200},
    )
    assert missed.json()["hearts"] == 2
    assert missed.json()["lost_heart"] is True
    assert "row" in missed.json()["message"]
    assert missed.json()["status"] == "playing"

    undone = client.post(f"/api/runs/{run['id']}/undo", json={"player_id": player["id"]})
    assert undone.json()["hearts"] == 3
    assert undone.json()["marks"] == [[wrong[0], wrong[1]]]

    restarted = client.post(f"/api/runs/{run['id']}/restart", json={"player_id": player["id"]})
    assert restarted.json()["hearts"] == 3
    assert restarted.json()["marks"] == []
    assert restarted.json()["elapsed_ms"] == 0

    dragged = client.post(
        f"/api/runs/{run['id']}/marks",
        json={"player_id": player["id"], "cells": [[0, 0], [0, 1]], "elapsed_ms": 300},
    )
    assert dragged.status_code == 200
    assert dragged.json()["hearts"] == 3
    assert len(dragged.json()["marks"]) >= 1

    current = restarted.json()
    for _ in range(40):
        if current["status"] == "won":
            break
        hinted = client.post(
            f"/api/runs/{current['id']}/hint",
            json={"player_id": player["id"], "elapsed_ms": 5000},
        )
        assert hinted.status_code == 200
        current = hinted.json()
        assert current["hearts"] == 3
        assert "solution" not in current
    assert current["status"] == "won"
    assert current["is_best"] is True
    assert current["hints"] >= 1

    home = client.get(f"/api/home?player_id={player['id']}")
    body = home.json()
    assert body["campaign_completed"] == 1
    assert body["campaign_next"] == 2
    assert body["stats"]["solved"] == 1


def test_next_campaign_level_is_a_different_board(client):
    player = _player(client, "Nia")
    first = client.post("/api/runs", json={"player_id": player["id"], "mode": "campaign", "level": 1}).json()
    current = first
    for _ in range(40):
        if current["status"] == "won":
            break
        current = client.post(
            f"/api/runs/{current['id']}/hint",
            json={"player_id": player["id"], "elapsed_ms": 1000},
        ).json()
    assert current["status"] == "won"
    assert current["title"] == "Level 1"
    second = client.post("/api/runs", json={"player_id": player["id"], "mode": "campaign", "level": 2}).json()
    assert second["title"] == "Level 2"
    assert second["id"] != first["id"]
    assert second["regions"] != first["regions"]
    assert second["status"] == "playing"


def test_daily_is_stable_and_counts_toward_the_streak(client):
    player = _player(client)
    first = client.post("/api/runs", json={"player_id": player["id"], "mode": "daily", "difficulty": "easy"})
    second = client.post("/api/runs", json={"player_id": player["id"], "mode": "daily", "difficulty": "easy"})
    assert first.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["regions"] == first.json()["regions"]

    current = first.json()
    cells = _solution(_puzzle_id(current["id"]))
    for row, col in cells:
        client.post(
            f"/api/runs/{current['id']}/tap",
            json={"player_id": player["id"], "row": row, "col": col, "elapsed_ms": 100},
        )
        placed = client.post(
            f"/api/runs/{current['id']}/tap",
            json={"player_id": player["id"], "row": row, "col": col, "elapsed_ms": 200},
        )
        current = placed.json()
    assert current["status"] == "won"
    home = client.get(f"/api/home?player_id={player['id']}").json()
    assert home["streak"] == 1
    assert home["daily"][0]["status"] == "won"


def test_endless_resume_and_new_board(client):
    player = _player(client, "Dee")
    first = client.post("/api/runs", json={"player_id": player["id"], "mode": "endless", "difficulty": "easy"})
    assert first.status_code == 200
    assert first.json()["size"] == 6
    resumed = client.post("/api/runs", json={"player_id": player["id"], "mode": "endless", "difficulty": "easy"})
    assert resumed.json()["id"] == first.json()["id"]
    fresh = client.post(
        "/api/runs",
        json={"player_id": player["id"], "mode": "endless", "difficulty": "easy", "replay": True},
    )
    assert fresh.status_code == 200
    assert fresh.json()["id"] != first.json()["id"]
    assert "solution" not in fresh.json()


def test_backup_round_trip(client):
    player = _player(client, "Cam")
    client.post("/api/runs", json={"player_id": player["id"], "mode": "campaign", "level": 1})
    exported = client.get("/api/admin/export")
    assert exported.status_code == 200
    payload = exported.json()
    assert payload["players"][0]["name"] == "Cam"
    assert "solution" in payload["puzzles"][0]

    client.delete(f"/api/players/{player['id']}")
    assert client.get(f"/api/home?player_id={player['id']}").status_code == 404

    restored = client.post("/api/admin/import", json=payload)
    assert restored.status_code == 200
    assert restored.json()["players"] == 1
    home = client.get(f"/api/home?player_id={player['id']}")
    assert home.status_code == 200
    assert home.json()["player"]["name"] == "Cam"
