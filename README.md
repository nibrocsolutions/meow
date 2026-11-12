# Meow

A phone-friendly cat logic puzzle for a Raspberry Pi. Place one cat in every row, every column, and every colored region, and don't let two cats touch — not even on a corner. Open it in the phone's browser. There is no app store install.

The rules are the ones people know from Meowdoku. This is a fan-made home version. It is not the official game and it is not affiliated with Oakever Games.

Built the same way as Dolf: one Python container, SQLite on a Docker volume, and a page served by that same container.

Meow listens on **port 8094**. The other apps already use 8000 (government-tracker), 8081 (math-facts and trip-planner), 8083 (health-tracker), 8085 (wifi-monitor), 8088 (kinney-aviation), and 8092 (dolf-tracker).

## Quick start (Raspberry Pi or any Docker host)

```bash
git clone https://github.com/nibrocsolutions/meow.git
cd meow
docker compose up -d --build
```

On the phone, join the same Wi-Fi as the Pi and open `http://<pi-ip>:8094`.

Add it to the home screen (Safari: Share → Add to Home Screen, Chrome: menu → Add to Home screen) and it opens like an app.

### Useful commands

```bash
docker compose logs -f
git pull && docker compose up -d --build
docker compose down
```

`docker compose down` keeps the `meow-data` volume. Add `-v` only when you mean to erase the puzzles and the saved games.

## What you can do

- Play a campaign. Early levels are 5×5 with one given cat. Later levels grow to 9×9
- Play today's easy, normal, and hard boards. The date follows the Pi's `DAILY_TZ` (Eastern Time by default) and the board is the same for everyone in the house
- Play endless puzzles at four sizes
- Tap a cell to mark it empty, tap again to try a cat, and drag to mark a line
- Lose a heart for a wrong cat. Three hearts end the attempt. Restart keeps the same board
- Ask for a hint. It explains the next forced step and does not cost a heart
- Undo a tap, a drag, or a hint
- Keep a separate record for each player name. The phone remembers which name you picked
- Read solved counts, the daily streak, and best times
- Open `http://<pi-ip>:8094/admin` to download a backup or replace the database from one

A level is saved the first time someone opens it, so a later update of the image does not change a board you have already started.

## How a board is made

Every board is generated on the Pi. The generator places cats so that none touch, grows a color around each cat, then nudges the borders until only one completion remains. It keeps the board only when that completion can be reached by the same eliminations the hint button uses: a row, column, or color with one open cell; a color stuck in one line; or one what-if. Guessing is never required. Wrong guesses still cost hearts.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
mkdir -p data
DATA_DIR=./data uvicorn app.main:app --reload --host 0.0.0.0 --port 8094
```

Tests:

```bash
pytest
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| GET, POST | `/api/players` | Names on this Pi |
| PATCH, DELETE | `/api/players/{id}` | Rename or remove a player |
| GET | `/api/home?player_id=` | Campaign, daily boards, streak, stats |
| POST | `/api/runs` | Start or resume a campaign level, a daily, or an endless board |
| GET | `/api/runs/{id}?player_id=` | The board, without the solution |
| POST | `/api/runs/{id}/tap` | Cycle empty → mark → cat |
| POST | `/api/runs/{id}/marks` | Mark the cells from a drag |
| POST | `/api/runs/{id}/undo` | Take back the last change |
| POST | `/api/runs/{id}/restart` | Hearts and marks back to the start |
| POST | `/api/runs/{id}/hint` | Explain and apply the next forced step |
| POST | `/api/runs/{id}/clock` | Save the timer |
| GET | `/api/admin/summary` | Counts |
| GET | `/api/admin/export` | Full backup, including solutions |
| POST | `/api/admin/import` | Replace the database from that backup |

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATA_DIR` | `./data` locally, `/data` in Docker | SQLite directory |
| `PORT` | `8094` | HTTP port |
| `DATABASE_URL` | `sqlite:///{DATA_DIR}/meow.db` | Override the database |
| `DAILY_TZ` | `America/New_York` | Which midnight rolls the daily boards |
| `TZ` | `America/New_York` in Docker | Clock inside the container |

## Notes

- Anyone who can open the address can play, and anyone who can open `/admin` can export or replace the whole database. The export includes puzzle solutions. Keep it on your home network. Do not forward port 8094 to the internet.
- The phone has to reach the Pi. On the same Wi-Fi, use the Pi's address. Away from home, use a VPN you already trust.
- Progress lives in SQLite on the Pi. The phone only remembers the player name.
- The page does not load fonts or puzzles from the internet. After the container is built, a round can be played with the Pi offline.
- The image is the multi-arch `python:3.12-slim` image, so it runs on a 64-bit Raspberry Pi and on a normal PC.

## Project layout

```
├── Dockerfile
├── docker-compose.yml
├── app/
│   ├── main.py
│   ├── puzzle.py
│   ├── game.py
│   ├── api/routes.py
│   └── static/
└── tests/
```
