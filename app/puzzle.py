"""Cat-region puzzles.

Place one cat in every row, every column, and every colored region.
Two cats may not touch, even on a corner. A fair board has one solution,
and that solution can be reached by elimination, singles, line locks,
and a single what-if — the same steps the hint button explains.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

UNKNOWN, CAT, MARK = 0, 1, 2

COLOR_NAMES = (
    "pink",
    "peach",
    "yellow",
    "lime",
    "sky",
    "blue",
    "lilac",
    "coral",
    "mint",
)

# Attempts per seed salt. The search is deterministic: the same seed always
# yields the same board, and a stubborn seed tries a later salt.
_SALTS = 8
_ATTEMPTS = 40
_REPAIR_STEPS = 450


class PuzzleError(Exception):
    """Raised when a seed cannot produce a fair board."""


@dataclass(frozen=True)
class Step:
    kind: str  # "cat" or "mark"
    cells: tuple[tuple[int, int], ...]
    text: str


@dataclass(frozen=True)
class GeneratedPuzzle:
    size: int
    regions: tuple[int, ...]
    solution: tuple[int, ...]  # column of the cat in each row
    starters: tuple[tuple[int, int], ...]

    @property
    def solution_cells(self) -> set[tuple[int, int]]:
        return {(row, col) for row, col in enumerate(self.solution)}


def campaign_profile(level: int) -> dict:
    if level < 1:
        raise ValueError("level must be at least 1")
    if level <= 3:
        size, starter, tier = 5, True, "Cozy"
    elif level <= 8:
        size, starter, tier = 6, True, "Easy"
    elif level <= 16:
        size, starter, tier = 7, True, "Normal"
    elif level <= 28:
        size, starter, tier = 7, False, "Normal"
    elif level <= 45:
        size, starter, tier = 8, False, "Hard"
    else:
        size, starter, tier = 9, False, "Expert"
    return {
        "level": level,
        "size": size,
        "starter": starter,
        "tier": tier,
        "seed": 10_000 + level * 997,
    }


ENDLESS = {
    "easy": {"size": 6, "starter": True, "tier": "Easy"},
    "normal": {"size": 7, "starter": True, "tier": "Normal"},
    "hard": {"size": 8, "starter": False, "tier": "Hard"},
    "expert": {"size": 9, "starter": False, "tier": "Expert"},
}

DAILY = {
    "easy": {"size": 6, "starter": True, "tier": "Easy"},
    "normal": {"size": 7, "starter": True, "tier": "Normal"},
    "hard": {"size": 8, "starter": False, "tier": "Hard"},
}


def daily_seed(day: str, difficulty: str) -> int:
    """day is YYYY-MM-DD. The number is stable for everyone on that date."""
    digits = int(day.replace("-", ""))
    offset = {"easy": 1, "normal": 2, "hard": 3}[difficulty]
    return digits * 10 + offset


def generate_puzzle(size: int, seed: int, starter: bool) -> GeneratedPuzzle:
    if size < 4 or size > 9:
        raise ValueError("size must be from 4 to 9")
    for salt in range(_SALTS):
        rng = random.Random((seed + salt * 1_000_003) & 0xFFFFFFFF)
        for _ in range(_ATTEMPTS):
            board = _attempt(size, rng)
            if board is None:
                continue
            regions, solution = board
            found = _deduced_solution(size, regions)
            if found is None or tuple(found) != tuple(solution):
                continue
            if _solution_count(size, regions, limit=2) != 1:
                continue
            starters: tuple[tuple[int, int], ...] = ()
            if starter:
                starters = (_pick_starter(size, regions, solution, rng),)
            # Region ids start out equal to the cat's row. Relabel them so the
            # color numbers on the wire are not a map of the solution.
            order = list(range(size))
            rng.shuffle(order)
            regions = [order[region] for region in regions]
            return GeneratedPuzzle(size, tuple(regions), tuple(solution), starters)
    raise PuzzleError(f"no fair {size}×{size} puzzle for seed {seed}")


def next_step(
    size: int,
    regions: list[int] | tuple[int, ...],
    cats: set[tuple[int, int]],
    marks: set[tuple[int, int]],
) -> Step | None:
    """The next human deduction, or None when nothing legal is forced."""
    state = [UNKNOWN] * (size * size)
    for row, col in cats:
        state[row * size + col] = CAT
    for row, col in marks:
        index = row * size + col
        if state[index] == UNKNOWN:
            state[index] = MARK
    cells = _region_cells(size, regions)
    shaded = state[:]
    if not _shade_from_cats(size, regions, cells, shaded):
        return None
    forced = _find_forced(size, regions, cells, shaded)
    if forced is not None:
        return forced
    locked = _find_line_lock(size, regions, cells, shaded)
    if locked is not None:
        return locked
    return _find_hypothetical(size, regions, cells, shaded)


def hint_for_player(
    size: int,
    regions: list[int] | tuple[int, ...],
    cats: set[tuple[int, int]],
    player_marks: set[tuple[int, int]],
) -> Step | None:
    """Next hint, skipping marks the player already wrote down.

    Player marks are notes. A mark sitting on the real cat is lifted by the
    hint that places that cat. Logic itself ignores stray notes.
    """
    logic_marks: set[tuple[int, int]] = set()
    for _ in range(size * size * 4):
        if len(cats) >= size:
            return None
        step = next_step(size, regions, cats, logic_marks)
        if step is None:
            return None
        if step.kind == "mark":
            logic_marks.update(step.cells)
            fresh = tuple(cell for cell in step.cells if cell not in player_marks and cell not in cats)
            if fresh:
                return Step("mark", fresh, step.text)
            continue
        cell = step.cells[0]
        if cell in cats:
            continue
        return step
    return None


def rejection_reason(
    size: int,
    regions: list[int] | tuple[int, ...],
    occupied: set[tuple[int, int]],
    row: int,
    col: int,
) -> str:
    """Why a cat cannot sit here, given the cats already on the board."""
    region = regions[row * size + col]
    for other_row, other_col in occupied:
        if (other_row, other_col) == (row, col):
            continue
        if other_row == row:
            return "That row already has a cat."
        if other_col == col:
            return "That column already has a cat."
        if regions[other_row * size + other_col] == region:
            return "That color already has a cat."
        if abs(other_row - row) <= 1 and abs(other_col - col) <= 1:
            return "Cats can't touch, even on a corner."
    return "That cell stays empty."


def regions_are_connected(size: int, regions: list[int] | tuple[int, ...]) -> bool:
    seen = [False] * (size * size)
    for start, region in enumerate(regions):
        if seen[start]:
            continue
        queue = deque([start])
        seen[start] = True
        count = 0
        while queue:
            index = queue.popleft()
            count += 1
            row, col = divmod(index, size)
            for d_row, d_col in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                next_row, next_col = row + d_row, col + d_col
                if not (0 <= next_row < size and 0 <= next_col < size):
                    continue
                neighbor = next_row * size + next_col
                if not seen[neighbor] and regions[neighbor] == region:
                    seen[neighbor] = True
                    queue.append(neighbor)
        if count == 0:
            return False
    return all(seen)


def solution_is_legal(size: int, regions: list[int] | tuple[int, ...], solution: list[int] | tuple[int, ...]) -> bool:
    if len(solution) != size:
        return False
    cols = set(solution)
    if len(cols) != size or any(col < 0 or col >= size for col in solution):
        return False
    used_regions = set()
    for row, col in enumerate(solution):
        region = regions[row * size + col]
        if region in used_regions:
            return False
        used_regions.add(region)
        if row and abs(solution[row - 1] - col) <= 1:
            return False
    return used_regions == set(range(size))


def _deduced_solution(size: int, regions: list[int]) -> list[int] | None:
    cats: set[tuple[int, int]] = set()
    marks: set[tuple[int, int]] = set()
    for _ in range(size * size * 4):
        if len(cats) == size:
            return [next(col for row, col in cats if row == index) for index in range(size)]
        step = next_step(size, regions, cats, marks)
        if step is None:
            return None
        if step.kind == "cat":
            cats.add(step.cells[0])
        else:
            marks.update(step.cells)
    return None


def _pick_starter(
    size: int,
    regions: list[int],
    solution: list[int],
    rng: random.Random,
) -> tuple[int, int]:
    sizes = [0] * size
    for region in regions:
        sizes[region] += 1
    ranked = sorted(
        ((sizes[regions[row * size + col]], row, col) for row, col in enumerate(solution)),
    )
    # Smallest region, with a shuffle only to break exact ties via the seed.
    smallest = ranked[0][0]
    tied = [(row, col) for size_n, row, col in ranked if size_n == smallest]
    rng.shuffle(tied)
    return tied[0]


def _attempt(size: int, rng: random.Random) -> tuple[list[int], list[int]] | None:
    solution = _place_cats(size, rng)
    if solution is None:
        return None
    regions = _grow_regions(size, solution, rng)
    repaired = _repair(size, regions, solution, rng)
    if repaired is None:
        return None
    return repaired, solution


def _place_cats(size: int, rng: random.Random) -> list[int] | None:
    cols: list[int] = []

    def search(row: int) -> bool:
        if row == size:
            return True
        options = list(range(size))
        rng.shuffle(options)
        for col in options:
            if col in cols:
                continue
            if cols and abs(cols[-1] - col) <= 1:
                continue
            cols.append(col)
            if search(row + 1):
                return True
            cols.pop()
        return False

    if not search(0):
        return None
    return cols[:]


def _grow_regions(size: int, cats: list[int], rng: random.Random) -> list[int]:
    regions = [-1] * (size * size)
    for row, col in enumerate(cats):
        regions[row * size + col] = row
    while True:
        options: list[tuple[float, int, int]] = []
        sizes = [0] * size
        for region in regions:
            if region >= 0:
                sizes[region] += 1
        for index, region in enumerate(regions):
            if region != -1:
                continue
            row, col = divmod(index, size)
            touching: set[int] = set()
            for d_row, d_col in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                next_row, next_col = row + d_row, col + d_col
                if 0 <= next_row < size and 0 <= next_col < size:
                    neighbor = regions[next_row * size + next_col]
                    if neighbor != -1:
                        touching.add(neighbor)
            for region_id in touching:
                weight = 1.0 / (sizes[region_id] ** 1.3)
                options.append((weight, index, region_id))
        if not options:
            break
        weights = [item[0] for item in options]
        pick = rng.choices(range(len(options)), weights=weights, k=1)[0]
        _, index, region_id = options[pick]
        regions[index] = region_id
    return regions


def _repair(
    size: int,
    regions: list[int],
    solution: list[int],
    rng: random.Random,
) -> list[int] | None:
    regions = regions[:]
    pinned = {row * size + col for row, col in enumerate(solution)}
    for _ in range(_REPAIR_STEPS):
        found = _solutions(size, regions, limit=2)
        if len(found) == 1 and found[0] == solution:
            return regions
        # The search stops at two completions. Those two may not include the
        # intended cats yet, so keep nudging borders until they do.
        if not found or (len(found) == 1 and found[0] != solution):
            return None
        alternate = found[0] if found[0] != solution else found[1]
        diffs = [row * size + alternate[row] for row in range(size) if alternate[row] != solution[row]]
        rng.shuffle(diffs)
        moved = False
        for index in diffs:
            if index in pinned:
                continue
            region_id = regions[index]
            if not _connected_without(size, regions, region_id, index):
                continue
            row, col = divmod(index, size)
            options: list[int] = []
            for d_row, d_col in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                next_row, next_col = row + d_row, col + d_col
                if not (0 <= next_row < size and 0 <= next_col < size):
                    continue
                neighbor = regions[next_row * size + next_col]
                if neighbor != region_id and neighbor not in options:
                    options.append(neighbor)
            if not options:
                continue
            regions[index] = rng.choice(options)
            moved = True
            break
        if not moved:
            return None
    return None


def _solutions(size: int, regions: list[int], limit: int) -> list[list[int]]:
    placed = [-1] * size
    used_cols = 0
    used_regions = 0
    found: list[list[int]] = []

    def candidates(row: int) -> list[int]:
        options = []
        for col in range(size):
            if used_cols & (1 << col):
                continue
            region_id = regions[row * size + col]
            if used_regions & (1 << region_id):
                continue
            if row and placed[row - 1] != -1 and abs(placed[row - 1] - col) <= 1:
                continue
            if row + 1 < size and placed[row + 1] != -1 and abs(placed[row + 1] - col) <= 1:
                continue
            options.append(col)
        return options

    def search(rows: list[int]) -> None:
        nonlocal used_cols, used_regions
        if len(found) >= limit:
            return
        if not rows:
            found.append(placed[:])
            return
        best_row = -1
        best: list[int] | None = None
        for row in rows:
            options = candidates(row)
            if not options:
                return
            if best is None or len(options) < len(best):
                best_row = row
                best = options
                if len(options) == 1:
                    break
        assert best is not None
        rows.remove(best_row)
        for col in best:
            region_id = regions[best_row * size + col]
            placed[best_row] = col
            used_cols |= 1 << col
            used_regions |= 1 << region_id
            search(rows)
            used_cols ^= 1 << col
            used_regions ^= 1 << region_id
            placed[best_row] = -1
            if len(found) >= limit:
                break
        rows.append(best_row)

    search(list(range(size)))
    return found


def _solution_count(size: int, regions: list[int] | tuple[int, ...], limit: int) -> int:
    return len(_solutions(size, list(regions), limit))


def _connected_without(size: int, regions: list[int], region_id: int, skip: int) -> bool:
    cells = [index for index, region in enumerate(regions) if region == region_id and index != skip]
    if not cells:
        return False
    seen = {cells[0]}
    queue = deque(cells[:1])
    while queue:
        index = queue.popleft()
        row, col = divmod(index, size)
        for d_row, d_col in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            next_row, next_col = row + d_row, col + d_col
            if not (0 <= next_row < size and 0 <= next_col < size):
                continue
            neighbor = next_row * size + next_col
            if neighbor == skip or neighbor in seen or regions[neighbor] != region_id:
                continue
            seen.add(neighbor)
            queue.append(neighbor)
    return len(seen) == len(cells)


def _region_cells(size: int, regions: list[int] | tuple[int, ...]) -> list[list[int]]:
    cells: list[list[int]] = [[] for _ in range(size)]
    for index, region in enumerate(regions):
        cells[region].append(index)
    return cells


def _shade_from_cats(
    size: int,
    regions: list[int] | tuple[int, ...],
    cells: list[list[int]],
    state: list[int],
) -> bool:
    """Mark every cell a placed cat rules out. One pass is enough."""
    for index, value in enumerate(state):
        if value != CAT:
            continue
        row, col = divmod(index, size)
        region_id = regions[index]
        for d_row in (-1, 0, 1):
            for d_col in (-1, 0, 1):
                if d_row == 0 and d_col == 0:
                    continue
                next_row, next_col = row + d_row, col + d_col
                if not (0 <= next_row < size and 0 <= next_col < size):
                    continue
                neighbor = next_row * size + next_col
                if state[neighbor] == CAT:
                    return False
        for other in range(size):
            for cell in (row * size + other, other * size + col):
                if cell != index and state[cell] == CAT:
                    return False
                if cell != index and state[cell] == UNKNOWN:
                    state[cell] = MARK
        for cell in cells[region_id]:
            if cell != index and state[cell] == CAT:
                return False
            if cell != index and state[cell] == UNKNOWN:
                state[cell] = MARK
    return True


def _open_cells(size: int, state: list[int], indexes: list[int]) -> list[int]:
    return [index for index in indexes if state[index] != MARK]


def _find_forced(
    size: int,
    regions: list[int] | tuple[int, ...],
    cells: list[list[int]],
    state: list[int],
) -> Step | None:
    groups: list[tuple[str, list[int]]] = []
    for row in range(size):
        groups.append(("row", [row * size + col for col in range(size)]))
    for col in range(size):
        groups.append(("column", [row * size + col for row in range(size)]))
    for region_id in range(size):
        groups.append(("region", cells[region_id]))
    for kind, group in groups:
        opens = _open_cells(size, state, group)
        cats = [index for index in opens if state[index] == CAT]
        if len(cats) > 1 or not opens:
            return None
        if cats or len(opens) != 1:
            continue
        row, col = divmod(opens[0], size)
        if kind == "row":
            text = f"Row {row + 1} has only one open cell."
        elif kind == "column":
            text = f"Column {col + 1} has only one open cell."
        else:
            text = f"The {COLOR_NAMES[regions[opens[0]]]} region has only one open cell."
        return Step("cat", ((row, col),), text)
    return None


def _find_line_lock(
    size: int,
    regions: list[int] | tuple[int, ...],
    cells: list[list[int]],
    state: list[int],
) -> Step | None:
    for region_id, group in enumerate(cells):
        opens = _open_cells(size, state, group)
        if not opens:
            return None
        rows = {index // size for index in opens}
        cols = {index % size for index in opens}
        if len(rows) == 1:
            row = next(iter(rows))
            marked = _unknown_outside_region(size, regions, state, region_id, row=row)
            if marked:
                name = COLOR_NAMES[region_id]
                text = (
                    f"The {name} region only fits in row {row + 1}, "
                    "so the other cells in that row stay empty."
                )
                return Step("mark", tuple(marked), text)
        if len(cols) == 1:
            col = next(iter(cols))
            marked = _unknown_outside_region(size, regions, state, region_id, col=col)
            if marked:
                name = COLOR_NAMES[region_id]
                text = (
                    f"The {name} region only fits in column {col + 1}, "
                    "so the other cells in that column stay empty."
                )
                return Step("mark", tuple(marked), text)
    for row in range(size):
        opens = [col for col in range(size) if state[row * size + col] != MARK]
        if not opens:
            return None
        region_ids = {regions[row * size + col] for col in opens}
        if len(region_ids) == 1:
            region_id = next(iter(region_ids))
            marked = [
                (index // size, index % size)
                for index in cells[region_id]
                if index // size != row and state[index] == UNKNOWN
            ]
            if marked:
                name = COLOR_NAMES[region_id]
                text = (
                    f"Row {row + 1}'s open cells are all {name}, "
                    "so the rest of that color stays empty."
                )
                return Step("mark", tuple(marked), text)
    for col in range(size):
        opens = [row for row in range(size) if state[row * size + col] != MARK]
        if not opens:
            return None
        region_ids = {regions[row * size + col] for row in opens}
        if len(region_ids) == 1:
            region_id = next(iter(region_ids))
            marked = [
                (index // size, index % size)
                for index in cells[region_id]
                if index % size != col and state[index] == UNKNOWN
            ]
            if marked:
                name = COLOR_NAMES[region_id]
                text = (
                    f"Column {col + 1}'s open cells are all {name}, "
                    "so the rest of that color stays empty."
                )
                return Step("mark", tuple(marked), text)
    return None


def _unknown_outside_region(
    size: int,
    regions: list[int] | tuple[int, ...],
    state: list[int],
    region_id: int,
    row: int | None = None,
    col: int | None = None,
) -> list[tuple[int, int]]:
    marked = []
    if row is not None:
        for col_index in range(size):
            index = row * size + col_index
            if regions[index] != region_id and state[index] == UNKNOWN:
                marked.append((row, col_index))
            if regions[index] != region_id and state[index] == CAT:
                return []
    if col is not None:
        for row_index in range(size):
            index = row_index * size + col
            if regions[index] != region_id and state[index] == UNKNOWN:
                marked.append((row_index, col))
            if regions[index] != region_id and state[index] == CAT:
                return []
    return marked


def _find_hypothetical(
    size: int,
    regions: list[int] | tuple[int, ...],
    cells: list[list[int]],
    state: list[int],
) -> Step | None:
    unknowns = [index for index, value in enumerate(state) if value == UNKNOWN]
    for index in unknowns:
        trial = state[:]
        trial[index] = CAT
        if not _settle(size, regions, cells, trial):
            row, col = divmod(index, size)
            text = (
                f"A cat in row {row + 1}, column {col + 1} "
                "leaves some other color with nowhere to sit."
            )
            return Step("mark", ((row, col),), text)
    for index in unknowns:
        trial = state[:]
        trial[index] = MARK
        if not _settle(size, regions, cells, trial):
            row, col = divmod(index, size)
            text = f"Row {row + 1}, column {col + 1} is the only cell that keeps every color alive."
            return Step("cat", ((row, col),), text)
    return None


def _settle(
    size: int,
    regions: list[int] | tuple[int, ...],
    cells: list[list[int]],
    state: list[int],
) -> bool:
    """Shade, place naked singles, and apply line locks. No what-if."""
    changed = True
    while changed:
        changed = False
        if not _shade_from_cats(size, regions, cells, state):
            return False
        groups: list[list[int]] = []
        for row in range(size):
            groups.append([row * size + col for col in range(size)])
        for col in range(size):
            groups.append([row * size + col for row in range(size)])
        groups.extend(cells)
        for group in groups:
            opens = _open_cells(size, state, group)
            if not opens:
                return False
            cats = [index for index in opens if state[index] == CAT]
            if len(cats) > 1:
                return False
            if not cats and len(opens) == 1:
                state[opens[0]] = CAT
                changed = True
        for region_id, group in enumerate(cells):
            opens = _open_cells(size, state, group)
            if not opens:
                return False
            rows = {index // size for index in opens}
            cols = {index % size for index in opens}
            if len(rows) == 1:
                row = next(iter(rows))
                for col in range(size):
                    index = row * size + col
                    if regions[index] == region_id:
                        continue
                    if state[index] == CAT:
                        return False
                    if state[index] == UNKNOWN:
                        state[index] = MARK
                        changed = True
            if len(cols) == 1:
                col = next(iter(cols))
                for row in range(size):
                    index = row * size + col
                    if regions[index] == region_id:
                        continue
                    if state[index] == CAT:
                        return False
                    if state[index] == UNKNOWN:
                        state[index] = MARK
                        changed = True
        for row in range(size):
            opens = [col for col in range(size) if state[row * size + col] != MARK]
            if not opens:
                return False
            region_ids = {regions[row * size + col] for col in opens}
            if len(region_ids) != 1:
                continue
            region_id = next(iter(region_ids))
            for index in cells[region_id]:
                if index // size == row:
                    continue
                if state[index] == CAT:
                    return False
                if state[index] == UNKNOWN:
                    state[index] = MARK
                    changed = True
        for col in range(size):
            opens = [row for row in range(size) if state[row * size + col] != MARK]
            if not opens:
                return False
            region_ids = {regions[row * size + col] for row in opens}
            if len(region_ids) != 1:
                continue
            region_id = next(iter(region_ids))
            for index in cells[region_id]:
                if index % size == col:
                    continue
                if state[index] == CAT:
                    return False
                if state[index] == UNKNOWN:
                    state[index] = MARK
                    changed = True
    cat_count = sum(value == CAT for value in state)
    if cat_count > size:
        return False
    return True
