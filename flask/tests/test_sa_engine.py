import pytest
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "optimization"))
from sa_engine import (
    Allocation, SAState, acceptance_criterion, is_valid_move,
    propose_single_cell_move, propose_block_swap, propose_boundary_diffusion,
    _neighbors, _cell_value, compute_delta, _cell_contrib,
    _init_greedy, run_sa, run_multi_chain,
    NROWS, NCOLS,
)
from data_layers import DataLayerLoader


@pytest.fixture
def loader():
    return DataLayerLoader(data_dir=Path(__file__).parent.parent / "optimization" / "data" / "mock")


@pytest.fixture
def small_loader():
    return DataLayerLoader(data_dir=Path(__file__).parent.parent / "optimization" / "data" / "mock")


class TestAllocation:
    def test_enum_values(self):
        assert Allocation.AGRICULTURE == 0
        assert Allocation.CONSERVATION == 1
        assert Allocation.INFRASTRUCTURE == 2
        assert len(Allocation) == 3

    def test_choices(self):
        choices = Allocation.choices()
        assert len(choices) == 3
        assert Allocation.AGRICULTURE in choices
        assert Allocation.CONSERVATION in choices
        assert Allocation.INFRASTRUCTURE in choices


class TestSAState:
    def test_init_default(self):
        state = SAState(1000)
        assert state.n_cells == 1000
        assert state.allocations.shape == (1000,)
        assert np.all(state.allocations == Allocation.AGRICULTURE)
        assert state.current_value == 0.0
        assert state.temperature == 1.0
        assert state.best_value == 0.0

    def test_init_with_allocations(self):
        allocs = np.array([0, 1, 2, 1, 0], dtype=np.int8)
        state = SAState(5, allocs)
        assert np.array_equal(state.allocations, allocs)
        assert state.allocations.dtype == np.int8

    def test_clone(self):
        state = SAState(100)
        state.current_value = 500.0
        state.best_value = 600.0
        clone = state.clone()
        assert clone.n_cells == state.n_cells
        assert clone.current_value == 500.0
        assert clone.best_value == 600.0
        assert np.array_equal(clone.allocations, state.allocations)

    def test_restore(self):
        state1 = SAState(100)
        state1.current_value = 500.0
        state2 = SAState(100)
        state2.allocations[:] = Allocation.CONSERVATION
        state2.current_value = 700.0
        state1.restore(state2)
        assert state1.current_value == 700.0
        assert np.all(state1.allocations == Allocation.CONSERVATION)


class TestAcceptanceCriterion:
    def test_positive_delta_always_accepted(self):
        assert acceptance_criterion(0.1, 0.5) is True
        assert acceptance_criterion(100.0, 0.001) is True

    def test_zero_delta_always_accepted(self):
        assert acceptance_criterion(0.0, 0.001) is True
        assert acceptance_criterion(0.0, 100.0) is True

    def test_negative_delta_high_temp_probability(self):
        np.random.seed(42)
        results = [acceptance_criterion(-1.0, 100.0) for _ in range(100)]
        assert any(results) is True

    def test_negative_delta_low_temp_rejected(self):
        np.random.seed(42)
        results = [acceptance_criterion(-1.0, 0.001) for _ in range(100)]
        assert all(r is False for r in results)


class TestNeighbors:
    def test_corner_top_left(self):
        nbrs = _neighbors(0)
        assert 1 in nbrs
        assert NCOLS in nbrs
        assert -1 not in nbrs
        assert -NCOLS not in nbrs

    def test_corner_bottom_right(self):
        idx = NROWS * NCOLS - 1
        nbrs = _neighbors(idx)
        assert idx - 1 in nbrs
        assert idx - NCOLS in nbrs
        assert idx + 1 not in nbrs
        assert idx + NCOLS not in nbrs

    def test_middle_cell(self):
        idx = NROWS * NCOLS // 2 + 1
        nbrs = _neighbors(idx, NROWS, NCOLS)
        assert len(nbrs) == 4
        assert idx - NCOLS in nbrs
        assert idx + NCOLS in nbrs
        assert idx - 1 in nbrs
        assert idx + 1 in nbrs


class TestCellValue:
    def test_basevalue_only(self):
        bv = np.zeros((10, 3), dtype=np.float32)
        bv[:, Allocation.AGRICULTURE] = 100.0
        bv[:, Allocation.CONSERVATION] = 50.0
        bv[:, Allocation.INFRASTRUCTURE] = 200.0
        fp = np.zeros(10, dtype=np.float32)
        rc = np.zeros(10, dtype=np.float32)

        assert _cell_value(0, Allocation.AGRICULTURE, bv, fp, rc) == 100.0
        assert _cell_value(0, Allocation.CONSERVATION, bv, fp, rc) == 50.0
        assert _cell_value(0, Allocation.INFRASTRUCTURE, bv, fp, rc) == 200.0

    def test_flood_penalty_agriculture(self):
        bv = np.zeros((10, 3), dtype=np.float32)
        bv[:, Allocation.AGRICULTURE] = 100.0
        fp = np.zeros(10, dtype=np.float32)
        fp[0] = 0.9
        rc = np.zeros(10, dtype=np.float32)

        val = _cell_value(0, Allocation.AGRICULTURE, bv, fp, rc)
        assert val < 100.0
        assert np.isclose(val, 100.0 - 1000.0 * 0.9)

    def test_flood_penalty_infrastructure(self):
        bv = np.zeros((10, 3), dtype=np.float32)
        bv[:, Allocation.INFRASTRUCTURE] = 500.0
        fp = np.zeros(10, dtype=np.float32)
        fp[0] = 0.6
        rc = np.zeros(10, dtype=np.float32)

        val = _cell_value(0, Allocation.INFRASTRUCTURE, bv, fp, rc)
        assert val < 500.0
        assert np.isclose(val, 500.0 - 1000.0 * 0.6)

    def test_road_access_bonus(self):
        bv = np.zeros((10, 3), dtype=np.float32)
        bv[:, Allocation.AGRICULTURE] = 100.0
        bv[:, Allocation.INFRASTRUCTURE] = 200.0
        fp = np.zeros(10, dtype=np.float32)
        rc = np.zeros(10, dtype=np.float32)
        rc[0] = 10.0
        assert _cell_value(0, Allocation.AGRICULTURE, bv, fp, rc) == 100.0 + 0.05 * 10.0
        assert _cell_value(0, Allocation.CONSERVATION, bv, fp, rc) == 0.0


class TestIsValidMove:
    def test_infra_high_flood_rejected(self):
        fp = np.array([0.95], dtype=np.float32)
        assert is_valid_move(0, Allocation.INFRASTRUCTURE, fp) is False

    def test_infra_low_flood_accepted(self):
        fp = np.array([0.5], dtype=np.float32)
        assert is_valid_move(0, Allocation.INFRASTRUCTURE, fp) is True

    def test_agriculture_always_accepted(self):
        fp = np.ones(10, dtype=np.float32)
        fp[:] = 0.99
        assert is_valid_move(0, Allocation.AGRICULTURE, fp) is True


class TestProposeMoves:
    def test_single_cell_changes_allocation(self):
        np.random.seed(42)
        state = SAState(100)
        state.allocations[:] = Allocation.AGRICULTURE
        cell, new_use = propose_single_cell_move(state)
        assert 0 <= cell < 100
        assert new_use != Allocation.AGRICULTURE

    def test_block_swap_returns_boundary_cell(self):
        np.random.seed(42)
        state = SAState(n_cells=NCOLS * 2, n_rows=2, n_cols=NCOLS)
        state.allocations[:NCOLS] = Allocation.AGRICULTURE
        state.allocations[NCOLS:] = Allocation.CONSERVATION
        cell, new_use = propose_block_swap(state)
        assert 0 <= cell < state.n_cells
        assert new_use in Allocation

    def test_boundary_diffusion_oscillates(self):
        np.random.seed(42)
        state = SAState(n_cells=NCOLS * 2, n_rows=2, n_cols=NCOLS)
        state.allocations[:] = Allocation.AGRICULTURE
        state.allocations[0] = Allocation.CONSERVATION
        cell, new_use = propose_boundary_diffusion(state)
        assert new_use in (Allocation.AGRICULTURE, Allocation.CONSERVATION)


class TestComputeDelta:
    def test_no_change_zero_delta(self):
        np.random.seed(42)
        state = SAState(10)
        bv = np.random.random((10, 3)).astype(np.float32)
        fp = np.zeros(10, dtype=np.float32)
        rc = np.zeros(10, dtype=np.float32)

        delta = compute_delta(5, Allocation(state.allocations[5]), state, bv, fp, rc, 0.0)
        assert delta == 0.0

    def test_delta_changes_with_new_use(self):
        np.random.seed(42)
        state = SAState(n_cells=10, n_rows=1, n_cols=10)
        state.allocations[:] = Allocation.AGRICULTURE
        bv = np.zeros((10, 3), dtype=np.float32)
        bv[:, Allocation.AGRICULTURE] = 100.0
        bv[:, Allocation.CONSERVATION] = 200.0
        fp = np.zeros(10, dtype=np.float32)
        rc = np.zeros(10, dtype=np.float32)

        delta = compute_delta(5, Allocation.CONSERVATION, state, bv, fp, rc, 0.0)
        assert delta > 0


class TestInitGreedy:
    def test_greedy_init_assigns_highest_value(self, loader):
        state = _init_greedy(loader)
        for i in range(state.n_cells):
            assigned = Allocation(state.allocations[i])
            basevals = [loader.basevalue[i, int(u)] for u in Allocation]
            max_val = max(basevals)
            assigned_val = loader.basevalue[i, assigned]
            assert assigned_val == max_val


class TestRunSA:
    def test_run_sa_improves_value(self, loader):
        np.random.seed(42)
        best = run_sa(
            loader,
            n_iterations=5000,
            initial_temperature=1.0,
            cooling_rate=0.95,
            progress_interval=5000,
            log_prefix="-test",
        )
        assert best.current_value > 0
        assert best.best_allocations.shape == (loader.n_cells,)

    def test_run_sa_respects_flood_constraint(self, loader):
        np.random.seed(42)
        best = run_sa(
            loader,
            n_iterations=2000,
            initial_temperature=0.1,
            log_prefix="-test",
        )
        for i in range(loader.n_cells):
            if Allocation(best.best_allocations[i]) == Allocation.INFRASTRUCTURE:
                assert loader.flood_probability[i] <= 0.9


class TestRunMultiChain:
    def test_multi_chain_returns_best(self, loader):
        best = run_multi_chain(
            loader,
            n_chains=3,
            n_iterations=1000,
            initial_temperature=0.1,
            log_prefix="-mctest",
        )
        assert best.current_value > 0
        assert best.best_allocations.shape == (loader.n_cells,)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
