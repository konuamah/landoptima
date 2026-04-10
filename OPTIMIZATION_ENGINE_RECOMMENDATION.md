# LandOptima Optimization Engine: Consultant Recommendation

> **Related:** [Constraints Status Document](../newdocmd) – Item #1 (Choose optimization formulation) is now **RESOLVED**

---

## Executive Summary

For LandOptima's West Africa land allocation problem, no single formulation dominates all criteria. However, given the policy planning use case (stakeholder negotiation, scenario exploration, interpretability requirements) and the scale (millions of cells), I recommend a hybrid two-stage approach:

- **Primary engine:** Spatial simulated annealing (heuristic) with problem-specific move generators
- **Fallback for small regions/validation:** Integer programming with aggregated planning units
- **Rule-based scoring** is rejected for core optimization due to its inability to enforce hard spatial constraints.

---

## 1. Evaluation Against Criteria

| Criterion | Heuristic (SA/GA) | IP with Aggregation | Rule-based Scoring |
|-----------|-------------------|---------------------|--------------------|
| **Contiguity enforcement** | Strong – penalty functions or move constraints | Weak to moderate – exponentially many constraints; aggregation helps but doesn't guarantee | None – impossible |
| **Feedback constraints** | Strong – arbitrary non-linear relationships | Weak – would require bilinear terms (non-convex) | None – cannot reference decisions |
| **Scale (millions of cells)** | Strong – O(n) per iteration, linear memory | Prohibitive – even aggregated to 1km² blocks yields ~10⁶ binary vars | Excellent – O(n) |
| **Solution quality vs. time** | Tunable – anytime algorithm, quality improves with runtime | Optimal but impractical at scale | Fixed – no optimization |

### Heuristic (Simulated Annealing / Genetic Algorithms)

- **Contiguity:** Enforced via (a) penalty terms in objective, (b) move generators that only swap boundaries, or (c) post-processing repair. SA with cluster moves works well.
- **Feedback constraints:** Natural fit. Example: road accessibility → allocate cell to ag only if adjacent cell allocated to infrastructure. This is a simple conditional in the objective evaluator.
- **Scale:** Linear scaling. 10M cells at 1km resolution: 10M objective evaluations per iteration. With 100K iterations → 1B evaluations. Optimize via sparse updates (only changed cells) → feasible.
- **Quality:** No optimality guarantee, but simulated annealing with geometric cooling converges in probability to global optimum given infinite time. In practice, excellent for spatial allocation problems.

### Integer Programming with Aggregation

- **Contiguity:** Requires flow-based constraints (e.g., Miller-Tucker-Zemlin for spatial connectivity) – adds O(n²) variables or constraints. Aggregation reduces cell count but destroys fine-scale boundaries needed for contiguity.
- **Feedback constraints:** "Road improves adjacent ag value" requires product of binary variables → bilinear → requires McCormick envelopes or piecewise linearization → accuracy loss and complexity explosion.
- **Scale:** At 10⁶ binary variables, commercial solvers (Gurobi, CPLEX) exhaust memory. Even at 10⁴ aggregated zones, contiguity constraints push solve times to hours/days.
- **Quality:** Optimal within linear relaxation gap. But optimality is meaningless if the formulation cannot represent real constraints.

### Rule-based Scoring (Weighted Overlay)

- **Contiguity:** Impossible to enforce as a hard constraint. Post-hoc merging of fragments destroys objective optimality.
- **Feedback constraints:** Cannot handle constraints that depend on allocation decisions. Road accessibility would require iterative recomputation (essentially becoming a heuristic anyway).
- **Scale:** Excellent – raster algebra at O(n).
- **Quality:** No optimization – just a ranking. Cannot trade off competing uses.

---

## 2. Recommended Approach: Spatial Simulated Annealing with Adaptive Moves

### Core formulation

**Decision variables:** For each cell *i*, discrete allocation *aᵢ* ∈ {agriculture, conservation, infrastructure}

**Objective (maximize):**

```
Z = Σᵢ [BaseValueᵢ(aᵢ)] + Σₖ λₖ · Penaltyₖ(allocations)
```

Where:
- **BaseValue** incorporates soil fertility, terrain stability, flood risk, seasonality
- **Penaltyₖ** includes:
  - Contiguity bonus for conservation blocks (pairwise similarity term)
  - Accessibility bonus (infrastructure-adjacent cells get higher ag value)
  - Compactness penalty (edge/area ratio)

**Hard constraints (enforced via infeasible move rejection):**
- Minimum conservation block size (connected component check)
- No infrastructure on flood zones
- No agriculture on steep slopes

### Why this fits LandOptima's use case

| Requirement | How SA addresses it |
|-------------|---------------------|
| Policy planning (scenario exploration) | SA is stochastic → run multiple times to generate solution ensembles, quantify tradeoffs |
| Stakeholder negotiation | Can fix certain cells as "mandatory" (pre-set allocations) and optimize around them |
| West Africa scale | Parallel tempering variant scales to 10M cells on commodity hardware |
| Interpretability | Final solution is a map; objective components can be reported as contribution heatmaps |

### Parameterization specific to LandOptima

- **Cooling schedule:** Geometric, *Tₖ₊₁ = 0.95·Tₖ*, with re-annealing every 500 iterations
- **Move set:**
  - Single-cell reassignment (80% probability)
  - Block swap (10% – swaps a connected cluster of same use to another use)
  - Boundary diffusion (10% – expands/shrinks conservation blocks at edges)
- **Contiguity enforcement:** Modified objective with Ising-like pairwise term: +bonus if neighbor has same use, weighted more heavily for conservation
- **Minimum block size:** After each move, check connected components for conservation; reject if component < threshold (except during early high-temperature phase)

---

## 3. Risks and Tradeoffs

### Heuristic (SA) Risks

| Risk | Mitigation |
|------|------------|
| No optimality guarantee | Run multiple chains (e.g., 10) with random seeds; present best + median + spread. For policy planning, "good enough" with known variance beats "optimal" from simplified model. |
| Parameter sensitivity | Autotune via initial experiments on 1% sample; use adaptive cooling (e.g., simulated annealing with reheating) |
| Fragmented conservation areas | Add strong spatial correlation term; use cluster moves that preserve contiguity; post-process with greedy merging |
| Long runtimes | Implement sparse evaluation (only recompute cells whose neighborhood changed). Target: 10M cells, 500K iterations → ~2 hours on 32-core machine |

### IP with Aggregation Risks

| Risk | Severity | Mitigation (if forced to use IP) |
|------|----------|----------------------------------|
| Contiguity constraints blow up | Critical | Use network flow formulation with O(n) constraints but lose compactness |
| Cannot handle feedback | High | Linearize via pre-computed adjacency weights (loses adaptive feedback) |
| Memory exhaustion | Critical at >50K cells | Decompose West Africa into 100km tiles; solve independently (ignores cross-tile contiguity) |

### Rule-based Scoring Risks

| Risk | Severity | Mitigation (if used) |
|------|----------|----------------------|
| No hard constraints | Critical – flood/terrain violations | Only use as initial solution generator for SA |
| No contiguity | Critical – conservation fragments useless | Not fixable; reject as standalone method |

### Key Tradeoff Decision for Client

**Quality vs. Speed:** SA gives 95% of achievable objective at 10% of the time needed to formulate + solve an aggregated IP that cannot represent feedback constraints. For West Africa policy planning, speed and constraint expressiveness dominate absolute optimality because:

- Input data (soil, flood risk) have ±20% uncertainty
- Stakeholders will modify constraints iteratively
- A near-optimal feasible solution today beats an optimal infeasible solution next month

---

## 4. Prototype Path Forward

### Phase 1: Feasibility & Calibration (2 weeks)

**Scope:** Ghana-first – all validation and calibration uses Ghana-specific data. Results establish the baseline before West Africa regional expansion.

**Data:** Extract 100km × 100km test region (southern Ghana) at 1km resolution → 10,000 cells

**Implement:**
- SA core with single-cell moves
- Objective: BaseValue + contiguity bonus (tunable λ)
- Hard constraints: flood/terrain exclusions

**Validation:** Compare against exhaustive search on 10×10 subregion (100 cells) to verify SA finds global optimum

**Output:** λ calibration curve, cooling schedule recommendation

### Phase 2: Full Constraints (3 weeks)

- Scope expands to Ghana national extent (~500km × 500km, ~250K cells) while maintaining single-country focus
- Add: Feedback constraints (road accessibility), minimum conservation block size (via connected components check after each move)
- Add: Cluster moves for efficiency
- Test: 1M cell region (e.g., 1000×1000) → target <30 minutes per run
- Parallel implementation: OpenMP for objective evaluation on neighborhoods

### Phase 3: Productionization (2 weeks)

- Multi-chain runs: 10 independent SA chains, report solution envelope
- Scenario interface: Fix cells to user-specified uses, re-optimize
- Export: GeoTIFF with allocation + per-cell objective contribution
- **Ghana policy validation:** Compare outputs against Ghana's existing land use plans and national statistics

### Phase 4 (Optional – if client demands optimality guarantee)

Hybrid refinement: Run SA to near-convergence, then extract aggregated zones (e.g., 5km patches of uniform allocation) and solve exact IP on the reduced problem (now ~4K variables) to certify gap.

---

## Final Recommendation

Adopt Spatial Simulated Annealing as the primary optimization engine. Reject rule-based scoring for core optimization. Reserve IP with aggregation for (a) small pilot regions or (b) final gap certification after SA produces a candidate solution.

The policy planning context in West Africa prioritizes flexibility, interpretability, and the ability to handle realistic spatial constraints over mathematical optimality. SA delivers all three at scale. The risks (no guarantee, parameter sensitivity) are manageable through multi-chain runs and autotuning – and are far less damaging than the risks of the alternatives (infeasibility for IP, no contiguity for scoring).

---

*Document version 1.0 – Consultant recommendation for LandOptima optimization engine selection*  
*April 2026*
