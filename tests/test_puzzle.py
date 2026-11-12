import pytest

from app.puzzle import (
    campaign_profile,
    generate_puzzle,
    next_step,
    regions_are_connected,
    rejection_reason,
    solution_is_legal,
)


def _solve(size, regions, cats):
    marks = set()
    cats = set(cats)
    for _ in range(size * size * 4):
        if len(cats) == size:
            return cats
        step = next_step(size, regions, cats, marks)
        assert step is not None
        if step.kind == "cat":
            assert step.cells[0] not in cats
            cats.add(step.cells[0])
        else:
            marks.update(step.cells)
    raise AssertionError("deduction stopped early")


@pytest.mark.parametrize("size,seed,starter", [(5, 1, True), (5, 2, False), (6, 4, True), (6, 8, False), (7, 3, True)])
def test_generated_board_is_fair(size, seed, starter):
    first = generate_puzzle(size, seed, starter)
    second = generate_puzzle(size, seed, starter)
    assert first == second
    assert len(first.regions) == size * size
    assert set(first.regions) == set(range(size))
    assert solution_is_legal(size, first.regions, first.solution)
    assert regions_are_connected(size, first.regions)
    solved = _solve(size, first.regions, set())
    assert solved == first.solution_cells
    if starter:
        assert len(first.starters) == 1
        assert first.starters[0] in first.solution_cells
        assert _solve(size, first.regions, set(first.starters)) == first.solution_cells
    else:
        assert first.starters == ()


def test_campaign_sizes_grow():
    assert campaign_profile(1)["size"] == 5
    assert campaign_profile(1)["starter"] is True
    assert campaign_profile(8)["size"] == 6
    assert campaign_profile(20)["starter"] is False
    assert campaign_profile(60)["size"] == 9
    with pytest.raises(ValueError):
        campaign_profile(0)


def test_rejection_names_the_rule():
    regions = [0, 0, 1, 1]
    message = rejection_reason(2, regions, {(0, 0)}, 0, 1)
    assert "row" in message
