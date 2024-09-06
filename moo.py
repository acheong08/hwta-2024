# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportMissingTypeArgument=false, reportUnknownParameterType=false, reportAny=false, reportUnknownArgumentType=false
import itertools
import json
import multiprocessing
import time
from typing import Any, override

import numpy as np
from numpy.typing import NDArray
from pymoo.algorithms.soo.nonconvex.pattern import PatternSearch
from pymoo.core.problem import Problem
from pymoo.optimize import minimize  # pyright: ignore[reportUnknownVariableType]

import solver.models as models
from constants import get_datacenters, get_demand, get_selling_prices, get_servers
from evaluation_v2 import Evaluator
from generate import generate
from reverse import get_solution
from utils import demand_to_map, sp_to_map

models.scale = 1

# REMEMBER TO OFFSET BY 1
MIN_TS = 1
MAX_TS = 168

SERVERS = get_servers()
DATACENTERS = get_datacenters()
SELLING_PRICES = get_selling_prices()

SERVER_MAP = {server.server_generation: server for server in SERVERS}
DATACENTER_MAP = {dc.datacenter_id: dc for dc in DATACENTERS}
SELLING_PRICES_MAP = sp_to_map(SELLING_PRICES)


# 1 for each combination but 2 for models.Action.MOVE
N_VAR = (MAX_TS - 1) * len(SERVERS) * len(models.ServerGeneration) * (1 + 1 + 2)


def demand_for(
    demand_map: dict[int, dict[models.ServerGeneration, dict[models.Sensitivity, int]]],
    ts: int,
    sg: models.ServerGeneration,
    sen: models.Sensitivity,
):
    return demand_map[ts].get(sg, {}).get(sen, 0)


class MyProblem(Problem):

    def __init__(
        self, demand: list[models.Demand], seed: int, time_limit: int = 60 * 60 * 6
    ):
        self.demand = demand_to_map(demand)
        self.best_score = 0
        self.best_solution: list[models.SolutionEntry] = []
        self.seed = seed

        self.time_limit = time_limit
        self.init_time = time.time()
        upper_bounds = np.zeros(N_VAR)
        n = 0
        for comb in itertools.product(
            range(MIN_TS, MAX_TS + 1),
            DATACENTER_MAP,
            models.ServerGeneration,
            models.Action,
        ):
            n_increment = 1 if comb[3] != models.Action.MOVE else 2
            if comb[0] == MIN_TS and comb[3] != models.Action.BUY:
                upper_bounds[n] = 0
                n += n_increment
                continue
            if (
                comb[0] < SERVER_MAP[comb[2]].release_time[0]
                or comb[0] > SERVER_MAP[comb[2]].release_time[1]
            ) and comb[3] == models.Action.BUY:
                upper_bounds[n] = 0
                n += n_increment
                continue
            if comb[3] == models.Action.MOVE:
                # Must be after release time
                if comb[0] > SERVER_MAP[comb[2]].release_time[0]:
                    upper_bounds[n] = 0
                    upper_bounds[n + 1] = 0
                upper_bounds[n] = (
                    DATACENTER_MAP[comb[1]].slots_capacity
                    // SERVER_MAP[comb[2]].slots_size
                )
                upper_bounds[n + 1] = len(DATACENTER_MAP) - 1
                n += n_increment
                continue
            upper_bounds[n] = (
                DATACENTER_MAP[comb[1]].slots_capacity // SERVER_MAP[comb[2]].slots_size
            )
            n += n_increment

        super().__init__(
            n_var=N_VAR,
            n_obj=1,
            n_ieq_constr=1,
            xl=np.zeros(N_VAR),
            xu=upper_bounds,
            vtype=int,
        )

    def evaluate_individual(self, x: NDArray[np.int64]) -> tuple[float, float]:
        actions = decode_actions(x)
        evaluator = Evaluator(
            actions, self.demand, SERVER_MAP, DATACENTER_MAP, SELLING_PRICES_MAP
        )
        valid_solution = evaluator.quick_validate()
        if valid_solution:
            score = evaluator.get_score()
            if score > self.best_score:
                self.best_score = score
                self.best_solution = actions
                print(self.seed, score)
            return -score, -1  # Negative score because we're minimizing, -1 for g
        else:
            return 0, 1  # 0 for f, 1 for g (constraint violation)

    @override
    def _evaluate(self, x: NDArray[np.int64], out: dict[str, Any]):
        if self.init_time + self.time_limit < time.time():
            print("time limit reached")
            print("Best score:", self.best_score)
            json.dump(
                generate(self.best_solution, SERVERS),
                open(f"output/{self.seed}.json", "w"),
            )
            time.sleep(100000000000000000)
        f, g = self.evaluate_individual(x[0])

        out["F"] = np.array(f)
        out["G"] = np.array(g)


def decode_actions(x: NDArray[np.int64]) -> list[models.SolutionEntry]:
    actions: list[models.SolutionEntry] = []
    n = 0
    for comb in itertools.product(
        range(MIN_TS, MAX_TS + 1),
        DATACENTER_MAP,
        models.ServerGeneration,
        models.Action,
    ):
        if x[n] == 0.0:
            n += 1 if comb[3] != models.Action.MOVE else 2
            continue
        amount = int(x[n])
        if comb[3] == models.Action.MOVE:
            actions.append(
                models.SolutionEntry(
                    comb[0],
                    comb[1],
                    comb[2],
                    models.Action.MOVE,
                    amount,
                    target_datacenter=DATACENTERS[int(x[n + 1])].datacenter_id,
                )
            )
            n += 2
        actions.append(
            models.SolutionEntry(
                comb[0],
                comb[1],
                comb[2],
                comb[3],
                amount,
            )
        )
        n += 1
    return actions


def actions_to_np(actions: list[models.SolutionEntry]) -> NDArray[np.int64]:
    action_map: dict[
        int,
        dict[models.ServerGeneration, dict[str, dict[models.Action, tuple[int, int]]]],
    ] = {}
    for action in actions:
        if action.timestep not in action_map:
            action_map[action.timestep] = {}
        if action.server_generation not in action_map[action.timestep]:
            action_map[action.timestep][action.server_generation] = {}
        if (
            action.datacenter_id
            not in action_map[action.timestep][action.server_generation]
        ):
            action_map[action.timestep][action.server_generation][
                action.datacenter_id
            ] = {}
        action_map[action.timestep][action.server_generation][action.datacenter_id][
            action.action
        ] = (
            action.amount,
            (
                DATACENTERS.index(DATACENTER_MAP[action.target_datacenter])
                if action.target_datacenter
                else 0
            ),
        )
    out = np.zeros(N_VAR, dtype=int)
    n = 0
    for comb in itertools.product(
        range(MIN_TS, MAX_TS + 1),
        DATACENTER_MAP,
        models.ServerGeneration,
        models.Action,
    ):
        if comb[3] == models.Action.MOVE:
            n += 2
            continue
        if comb[0] not in action_map:
            n += 1
            continue
        if comb[2] not in action_map[comb[0]]:
            n += 1
            continue
        if comb[1] not in action_map[comb[0]][comb[2]]:
            n += 1
            continue
        if comb[3] not in action_map[comb[0]][comb[2]][comb[1]]:
            n += 1
            continue

        out[n] = action_map[comb[0]][comb[2]][comb[1]][comb[3]][0]
        n += 1
    print("Done decoding")
    return out


def action_to_dict(a: list[models.SolutionEntry]):
    b: list[dict[str, Any]] = []
    for i in a:
        b.append(i.to_dict())
    return b


def run_moo(seed: int):

    initial_solution = actions_to_np(get_solution(f"merged/{seed}.json"))
    algorithm = PatternSearch(x0=initial_solution)
    np.random.seed(seed)
    demand = get_demand()

    problem = MyProblem(demand, seed)
    res: None | Any = minimize(problem, algorithm)  # type: ignore[reportUnknownVariableType]
    if res is None or res.X is None:
        print("No solution found")
        return

    best_solution = decode_actions(res.X)
    best_score = Evaluator(
        best_solution, demand, SERVER_MAP, DATACENTER_MAP, SELLING_PRICES_MAP
    ).get_score()
    print(f"Best score: {best_score}")


if __name__ == "__main__":
    seeds = [3329, 4201, 8761, 2311, 2663, 4507, 6247, 2281, 4363, 5693]

    with multiprocessing.Pool() as pool:
        results = pool.map(run_moo, seeds)

    for result in results:
        print(result)

    print("All runs completed.")
