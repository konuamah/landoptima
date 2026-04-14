#!/usr/bin/env python3
"""
SA Engine — Spatial Simulated Annealing for LandOptima land allocation.

Maximizes economic value across Ghana's 504,000 grid cells by assigning each
to agriculture, conservation, or infrastructure — subject to flood/slope hard
constraints and a contiguity soft penalty (Ising term).

Key design: sparse delta evaluation. Each proposed move only re-evaluates
the changed cell + its 4 neighbors (O(1)) instead of the full grid (O(n)).
This makes 100K-iteration runs feasible on a single laptop.
"""

import logging
import random
import time
from enum import IntEnum
from typing import Optional, Tuple

import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

NROWS = 840
NCOLS = 600


class Allocation(IntEnum):
    AGRICULTURE = 0
    CONSERVATION = 1
    INFRASTRUCTURE = 2

    @classmethod
    def choices(cls):
        return list(cls)


class SAState:
    """Holds current SA solution state."""

    def __init__(
        self,
        n_cells: int,
        allocations: Optional[np.ndarray] = None,
        n_rows: Optional[int] = None,
        n_cols: Optional[int] = None,
    ):
        self.n_cells = n_cells
        if n_rows is not None and n_cols is not None:
            self.n_rows = n_rows
            self.n_cols = n_cols
        elif n_rows is not None:
            self.n_rows = n_rows
            self.n_cols = n_cells // n_rows if n_rows > 0 else NCOLS
        elif n_cols is not None:
            self.n_cols = n_cols
            self.n_rows = n_cells // n_cols if n_cols > 0 else NROWS
        else:
            self.n_rows = NROWS
            self.n_cols = NCOLS
        if allocations is not None:
            self.allocations = allocations.astype(np.int8)
        else:
            self.allocations = np.full(n_cells, Allocation.AGRICULTURE, dtype=np.int8)
        self.current_value = 0.0
        self.temperature = 1.0
        self.best_value = 0.0
        self.best_allocations = self.allocations.copy()
        self.iteration = 0

    def clone(self) -> "SAState":
        """Deep copy of state."""
        other = SAState(self.n_cells, self.allocations.copy(), self.n_rows, self.n_cols)
        other.current_value = self.current_value
        other.temperature = self.temperature
        other.best_value = self.best_value
        other.best_allocations = self.best_allocations.copy()
        other.iteration = self.iteration
        return other

    def restore(self, other: "SAState"):
        """Restore from a cloned state."""
        self.allocations[:] = other.allocations
        self.current_value = other.current_value
        self.temperature = other.temperature
        self.best_value = other.best_value
        self.best_allocations[:] = other.best_allocations
        self.iteration = other.iteration


def _neighbors(cell_idx: int, n_rows: int = NROWS, n_cols: int = NCOLS) -> list:
    """Return flat array indices of 4-connected neighbors of a cell."""
    row = cell_idx // n_cols
    col = cell_idx % n_cols
    nbrs = []
    if row > 0:
        nbrs.append(cell_idx - n_cols)
    if row < n_rows - 1:
        nbrs.append(cell_idx + n_cols)
    if col > 0:
        nbrs.append(cell_idx - 1)
    if col < n_cols - 1:
        nbrs.append(cell_idx + 1)
    return nbrs


def acceptance_criterion(delta: float, temperature: float) -> bool:
    """
    Metropolis acceptance: accept if delta >= 0 (improving move),
    otherwise accept with probability exp(-delta / T).
    """
    if delta >= 0:
        return True
    if temperature <= 1e-10:
        return False
    if delta / temperature < -700:
        return False
    return np.random.rand() < np.exp(delta / temperature)


def _neighbors(cell_idx: int, n_rows: int = NROWS, n_cols: int = NCOLS) -> list:
    """Return flat array indices of 4-connected neighbors of a cell."""
    row = cell_idx // n_cols
    col = cell_idx % n_cols
    nbrs = []
    if row > 0:
        nbrs.append(cell_idx - n_cols)
    if row < n_rows - 1:
        nbrs.append(cell_idx + n_cols)
    if col > 0:
        nbrs.append(cell_idx - 1)
    if col < n_cols - 1:
        nbrs.append(cell_idx + 1)
    return nbrs


def _cell_value(
    cell_idx: int,
    alloc: Allocation,
    basevalue: np.ndarray,
    flood_prob: np.ndarray,
    road_cost: np.ndarray,
) -> float:
    """
    Economic value of a single cell for a given allocation.
    Includes road access bonus and flood penalty.
    """
    val = basevalue[cell_idx, alloc]

    flood_p = flood_prob[cell_idx]
    if alloc == Allocation.INFRASTRUCTURE and flood_p > 0.5:
        val -= 1000.0 * flood_p
    if alloc == Allocation.AGRICULTURE and flood_p > 0.8:
        val -= 1000.0 * flood_p

    if alloc in (Allocation.AGRICULTURE, Allocation.INFRASTRUCTURE):
        val += 0.05 * road_cost[cell_idx]

    return val


def _cell_contrib(
    cell_idx: int,
    alloc: Allocation,
    allocs: np.ndarray,
    basevalue: np.ndarray,
    flood_prob: np.ndarray,
    road_cost: np.ndarray,
    lambda_contiguity: float,
    n_rows: int = NROWS,
    n_cols: int = NCOLS,
) -> float:
    """
    Full contribution of a cell to the objective: base value + half of each
    neighbor's contiguity bonus (to avoid double-counting when summing over all cells).
    """
    val = _cell_value(cell_idx, alloc, basevalue, flood_prob, road_cost)

    if lambda_contiguity == 0:
        return val

    my_alloc = alloc
    for n_idx in _neighbors(cell_idx, n_rows, n_cols):
        if allocs[n_idx] == my_alloc:
            weight = 2.0 if my_alloc == Allocation.CONSERVATION else 1.0
            val += 0.5 * lambda_contiguity * weight

    return val


def compute_delta(
    cell_idx: int,
    new_alloc: Allocation,
    state: SAState,
    basevalue: np.ndarray,
    flood_prob: np.ndarray,
    road_cost: np.ndarray,
    lambda_contiguity: float,
) -> float:
    """
    Sparse delta: compute value change from reallocating cell_idx to new_alloc.
    Only recomputes the changed cell and its 4 neighbors (O(1) not O(n)).
    """
    old_alloc = state.allocations[cell_idx]
    if old_alloc == new_alloc:
        return 0.0

    affected = {cell_idx} | set(_neighbors(cell_idx, state.n_rows, state.n_cols))

    old_total = 0.0
    new_total = 0.0
    for idx in affected:
        old_total += _cell_contrib(
            idx,
            state.allocations[idx],
            state.allocations,
            basevalue,
            flood_prob,
            road_cost,
            lambda_contiguity,
            state.n_rows,
            state.n_cols,
        )
        new_alloc_for_idx = new_alloc if idx == cell_idx else state.allocations[idx]
        new_total += _cell_contrib(
            idx,
            new_alloc_for_idx,
            state.allocations,
            basevalue,
            flood_prob,
            road_cost,
            lambda_contiguity,
            state.n_rows,
            state.n_cols,
        )

    return new_total - old_total


def is_valid_move(
    cell_idx: int,
    alloc: Allocation,
    flood_prob: np.ndarray,
    max_flood_for_infra: float = 0.9,
) -> bool:
    """
    Hard constraint check: reject infrastructure on very high flood-probability cells.
    """
    if alloc == Allocation.INFRASTRUCTURE and flood_prob[cell_idx] > max_flood_for_infra:
        return False
    return True


def propose_single_cell_move(state: SAState) -> Tuple[int, Allocation]:
    """80% move: pick random cell, reassign to different random use."""
    cell = np.random.randint(0, state.n_cells)
    current = Allocation(state.allocations[cell])
    proposals = [u for u in Allocation if u != current]
    new_use = random.choice(proposals)
    return cell, new_use


def propose_block_swap(state: SAState) -> Tuple[int, Allocation]:
    """
    10% move: start from a random boundary cell (cell with at least one neighbor
    of a different use), grow a small BFS cluster, swap all to a uniform new use.
    """
    boundary_cells = []
    for idx in range(state.n_cells):
        alloc = state.allocations[idx]
        for n in _neighbors(idx, state.n_rows, state.n_cols):
            if state.allocations[n] != alloc:
                boundary_cells.append(idx)
                break

    if not boundary_cells:
        return propose_single_cell_move(state)

    start = random.choice(boundary_cells)
    target_alloc = state.allocations[start]
    new_alloc = random.choice([u for u in Allocation if u != target_alloc])

    cluster = {start}
    frontier = {start}
    max_cluster = random.randint(10, 50)

    while frontier and len(cluster) < max_cluster:
        next_frontier = set()
        for idx in frontier:
            for n in _neighbors(idx, state.n_rows, state.n_cols):
                if n not in cluster and state.allocations[n] == target_alloc:
                    cluster.add(n)
                    next_frontier.add(n)
        frontier = next_frontier

    cell = random.choice(list(cluster))
    return cell, new_alloc


def propose_boundary_diffusion(state: SAState) -> Tuple[int, Allocation]:
    """
    10% move: pick a random conservation/agriculture boundary cell and
    flip it to the opposite use, nudging the boundary.
    """
    boundary_cells = []
    for idx in range(state.n_cells):
        alloc = state.allocations[idx]
        if alloc not in (Allocation.CONSERVATION, Allocation.AGRICULTURE):
            continue
        for n in _neighbors(idx, state.n_rows, state.n_cols):
            if state.allocations[n] != alloc:
                boundary_cells.append(idx)
                break

    if not boundary_cells:
        return propose_single_cell_move(state)

    cell = random.choice(boundary_cells)
    current = Allocation(state.allocations[cell])
    new_use = Allocation.AGRICULTURE if current == Allocation.CONSERVATION else Allocation.CONSERVATION
    return cell, new_use


def _init_greedy(data) -> SAState:
    """
    Greedy initialization: assign each cell to its highest-basevalue use.
    Faster convergence than uniform agriculture start.
    """
    n_cells = data.n_cells
    n_rows = data.n_rows
    n_cols = data.n_cols
    allocs = np.full(n_cells, Allocation.AGRICULTURE, dtype=np.int8)

    for i in range(n_cells):
        best_use = Allocation.AGRICULTURE
        best_val = data.basevalue[i, Allocation.AGRICULTURE]
        for use in Allocation:
            val = data.basevalue[i, use]
            if val > best_val:
                best_val = val
                best_use = use
        allocs[i] = best_use

    state = SAState(n_cells, allocs, n_rows=n_rows, n_cols=n_cols)
    bv = data.basevalue
    fp = data.flood_probability
    rc = data.road_cost

    total = 0.0
    for i in range(n_cells):
        total += _cell_value(i, Allocation(allocs[i]), bv, fp, rc)
    state.current_value = total
    state.best_value = total
    state.best_allocations = allocs.copy()

    logger.info(f"[SA] Greedy init complete. Initial value: {total:,.0f}")
    return state


def _autotune_temperature(data, n_test: int = 1000) -> float:
    """
    Auto-tune initial temperature by running n_test random moves and setting T
    so that ~50% of moves are accepted at the start.
    """
    state = _init_greedy(data)
    deltas = []

    for _ in range(n_test):
        cell = np.random.randint(0, state.n_cells)
        new_use = random.choice([u for u in Allocation if u != Allocation(state.allocations[cell])])
        if not is_valid_move(cell, new_use, data.flood_probability):
            continue
        delta = compute_delta(
            cell, new_use, state,
            data.basevalue, data.flood_probability, data.road_cost,
            lambda_contiguity=0.1,
        )
        deltas.append(delta)

    if not deltas:
        return 1.0

    mean_delta = np.mean(deltas)
    std_delta = np.std(deltas)
    T = max(abs(mean_delta) + std_delta, 0.01)
    logger.info(f"[SA] Autotuned T={T:.4f} from {len(deltas)} sample moves (mean_delta={mean_delta:.2f}, std={std_delta:.2f})")
    return float(T)


def run_sa(
    data,
    n_iterations: Optional[int] = None,
    initial_temperature: Optional[float] = None,
    cooling_rate: float = 0.95,
    reheat_interval: int = 500,
    lambda_contiguity: float = 0.1,
    lambda_access: float = 0.05,
    weight_infra: float = 1000.0,
    random_seed: Optional[int] = None,
    progress_interval: int = 10000,
    log_prefix: str = "",
) -> SAState:
    """
    Run simulated annealing on the Ghana grid.

    Args:
        data: DataLayerLoader instance with basevalue, flood_probability, road_cost
        n_iterations: number of iterations (default: max(100_000, n_cells // 5))
        initial_temperature: starting temperature (default: autotuned)
        cooling_rate: geometric cooling multiplier (default 0.95)
        reheat_interval: iterations between reheat events (default 500)
        lambda_contiguity: Ising contiguity bonus weight
        lambda_access: road access bonus weight
        weight_infra: flood penalty multiplier
        random_seed: RNG seed for reproducibility
        progress_interval: log progress every N iterations
        log_prefix: prefix for log messages (e.g., "chain-3")

    Returns:
        SAState with best found allocations
    """
    if random_seed is not None:
        np.random.seed(random_seed)
        random.seed(random_seed)

    n_cells = data.n_cells
    if n_iterations is None:
        n_iterations = max(100_000, n_cells // 5)

    logger.info(f"[SA{log_prefix}] Starting SA: {n_iterations:,} iterations, {n_cells:,} cells")

    if initial_temperature is None:
        initial_temperature = _autotune_temperature(data)

    state = _init_greedy(data)
    T = initial_temperature
    state.temperature = T

    best = state.clone()
    start_time = time.time()

    for i in range(n_iterations):
        state.iteration = i

        r = np.random.rand()
        if r < 0.80:
            cell, new_use = propose_single_cell_move(state)
        elif r < 0.90:
            cell, new_use = propose_block_swap(state)
        else:
            cell, new_use = propose_boundary_diffusion(state)

        if not is_valid_move(cell, new_use, data.flood_probability):
            continue

        delta = compute_delta(
            cell, new_use, state,
            data.basevalue, data.flood_probability, data.road_cost,
            lambda_contiguity,
        )

        if acceptance_criterion(delta, T):
            state.allocations[cell] = new_use
            state.current_value += delta

        if state.current_value > best.current_value:
            best.restore(state)

        T *= cooling_rate
        if reheat_interval > 0 and (i + 1) % reheat_interval == 0 and i > 0:
            T = initial_temperature * 0.5
            state.temperature = T

        if (i + 1) % progress_interval == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            eta = (n_iterations - i - 1) / rate if rate > 0 else 0
            logger.info(
                f"[SA{log_prefix}] iter {i+1:,}/{n_iterations:,} "
                f"cur={state.current_value:,.0f} best={best.current_value:,.0f} "
                f"T={T:.6f} rate={rate:,.0f}/s eta={eta:.0f}s"
            )

    elapsed = time.time() - start_time
    logger.info(
        f"[SA{log_prefix}] Done. {n_iterations:,} iterations in {elapsed:.1f}s "
        f"({n_iterations/elapsed:,.0f} iter/s). "
        f"Best value: {best.current_value:,.0f}"
    )
    return best


def run_multi_chain(
    data,
    n_chains: int = 10,
    n_iterations: Optional[int] = None,
    initial_temperature: Optional[float] = None,
    cooling_rate: float = 0.95,
    reheat_interval: int = 500,
    lambda_contiguity: float = 0.1,
    lambda_access: float = 0.05,
    weight_infra: float = 1000.0,
    max_workers: Optional[int] = None,
) -> SAState:
    """
    Run n independent SA chains in parallel, return the best.

    Args:
        data: DataLayerLoader instance
        n_chains: number of parallel chains (default 10)
        All other args passed through to run_sa()

    Returns:
        Best SAState from all chains
    """
    if max_workers is None:
        max_workers = n_chains

    logger.info(f"[SA] Starting {n_chains} parallel chains...")

    def chain_runner(chain_idx: int) -> SAState:
        prefix = f"-c{chain_idx}"
        return run_sa(
            data=data,
            n_iterations=n_iterations,
            initial_temperature=initial_temperature,
            cooling_rate=cooling_rate,
            reheat_interval=reheat_interval,
            lambda_contiguity=lambda_contiguity,
            lambda_access=lambda_access,
            weight_infra=weight_infra,
            random_seed=42 + chain_idx,
            log_prefix=prefix,
        )

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(chain_runner, i): i for i in range(n_chains)}
        for future in as_completed(futures):
            chain_idx = futures[future]
            try:
                result = future.result()
                results.append((chain_idx, result))
                logger.info(f"[SA] Chain {chain_idx} done: value={result.current_value:,.0f}")
            except Exception as e:
                logger.error(f"[SA] Chain {chain_idx} failed: {e}")

    best = max(results, key=lambda x: x[1].current_value)
    logger.info(
        f"[SA] Multi-chain complete. Best: chain {best[0]}, value={best[1].current_value:,.0f}"
    )
    return best[1]
