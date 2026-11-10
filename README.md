# Profit-Maximizing Student Scheduling with Simulated Annealing

A simulated annealing heuristic (pure Python) that assigns ~1000 customer orders to 20 students and sequences their routes to maximize net profit, subject to an 8-hour shift limit and per-order skill requirements.

Group project for **Modeling & Computing (EBC2180)**, Maastricht University School of Business and Economics, Period 4 (submitted March 2026).

**Authors:** Jelle Hermans, Sergejs Gorevs

## Problem

20 students start and end each day at a headquarters (node 251) and visit customers to carry out paid orders.

- Each order has a location, a duration, a profit and a list of students who have the skills to do it
- A student's route (driving plus order time) may not exceed 8 hours
- Every hour of work or driving costs €60, so the objective is **net profit = order revenue − time cost**
- Not every order has to be served, and an unprofitable order should be skipped

## Approach

1. **Greedy initial solution.** Orders are sorted by profit density (€ per second) and each is inserted at the best feasible position among the students eligible for it.
2. **Simulated annealing.** Millions of small moves are proposed per run; improvements are always accepted, and worse moves are accepted with probability `exp(Δprofit / T)`.
3. **Incremental evaluation.** Every move is scored with O(1) delta-time formulas that only look at the edges that change, and each student's route time is cached for instant shift-limit checks. The solver reaches roughly 350,000 iterations per second.
4. **Reheating.** Once the temperature hits its floor and nothing has improved for 10 seconds, the temperature is raised again (randomized factor) to escape local optima.
5. **Checkpointing.** The best solution found so far is written to `sol.txt` every 5 seconds.

| Parameter | Value |
|---|---|
| Start temperature | 12.5 |
| Minimum temperature | 0.03 |
| Cooling | geometric, ×0.99999997 per iteration |
| Reheat trigger | 10 s without improvement at minimum temperature |
| Default run time | 300 s |

### Neighbourhood operators

| Operator | Weight | What it does |
|---|---|---|
| `relocate` | 35% | Moves an order to a random position in the same or another eligible student's route |
| `add` | 30% | Inserts a random unassigned order at a random position (a greedy best-insertion variant, `op_add`, is also included) |
| `2-opt` | 20% | Reverses a random segment of one route to remove crossing paths |
| `remove` | 15% | Takes a random order out of a route |
| `swap` | 10% | Exchanges two orders between two students (skill-checked) |

### Weighting experiments

We tested two adaptive schemes for choosing operators: weights that depend on the temperature (explorer operators favoured when hot, refiners when cold), and an Adaptive Large Neighborhood Search style scheme that rescores operators by their Δprofit every ~10,000 iterations. Neither beat the static weights above, so the final solver uses static weights. The hook for dynamic weighting (`update_operator_weights`) is left in the code.

## Result

The included example output, [`sol.txt`](sol.txt), reaches a **net profit of €9,533** with **888 orders** scheduled across the 20 students.

## Running it

Requires Python 3 and the standard library only.

```bash
python Programming_Assignment_EBC2180-1.py
```

The script expects two input files in the same folder. They are course data and are **not included in this repository**:

- `drivingtimes.txt`: square matrix of driving times in seconds, whitespace-separated
- `orders.txt`: tab-separated with a header row; the order ID is in column 0, the node in column 2, the duration in minutes in column 5, the profit in column 6, and 20 skill flags (one per student) in columns 7–26

The run time is set in `main()` (`runtime_limit_seconds`). A progress dashboard prints every 3 seconds with elapsed time, iterations, temperature, current and best profit, customers served, iterations per second and per-operator acceptance rates.

### Output format (`sol.txt`)

```
<net profit>
<number of orders for student 0>
<order ID>
<order ID>
...
<number of orders for student 1>
...
```

## Repository contents

| File | Description |
|---|---|
| `Programming_Assignment_EBC2180-1.py` | Solver (greedy initialization, operators, simulated annealing loop) |
| `sol.txt` | Example solution output |
| `Programming_Assignment_Report.pdf` | Short written report on the solution and the weighting experiments |
