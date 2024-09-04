# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportMissingTypeArgument=false, reportUnknownParameterType=false, reportAny=false
import itertools
from typing import Any, override

import numpy as np
from numpy.typing import NDArray
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.problem import Problem
from pymoo.optimize import minimize  # pyright: ignore[reportUnknownVariableType]

from constants import get_datacenters, get_demand, get_selling_prices, get_servers
from evaluation_v2 import Evaluator
from solver.models import Action, Demand, ServerGeneration, SolutionEntry
from utils import demand_to_map, sp_to_map

# REMEMBER TO OFFSET BY 1
MIN_TS = 0
MAX_TS = 167

SERVERS = get_servers()
DATACENTERS = get_datacenters()
SELLING_PRICES = get_selling_prices()

SERVER_MAP = {server.server_generation: server for server in SERVERS}
DATACENTER_MAP = {dc.datacenter_id: dc for dc in DATACENTERS}
SELLING_PRICES_MAP = sp_to_map(SELLING_PRICES)


class MyProblem(Problem):

    def __init__(
        self,
        demand: list[Demand],
    ):
        self.demand = demand_to_map(demand)
        n_var = MAX_TS * len(SERVERS) * len(ServerGeneration) * len(Action)

        upper_bounds = np.array([1] * n_var)
        for n, comb in enumerate(
            itertools.product(
                range(MIN_TS, MAX_TS), DATACENTER_MAP, ServerGeneration, Action
            )
        ):
            if comb[0] == 0 and comb[3] != Action.BUY:
                upper_bounds[n] = 0
                continue
            upper_bounds[n] = (
                SERVER_MAP[comb[2]].slots_size // DATACENTER_MAP[comb[1]].slots_capacity
            )

        super().__init__(
            n_var=n_var,
            n_obj=1,
            n_constr=0,
            xl=np.zeros(n_var),
            xu=upper_bounds,
        )

    def decode_actions(self, x: NDArray[np.float64]) -> list[SolutionEntry]:
        actions: list[SolutionEntry] = []
        for n, comb in enumerate(
            itertools.product(
                range(MIN_TS, MAX_TS), DATACENTER_MAP, ServerGeneration, Action
            )
        ):
            if x[n] == 0:
                continue
            actions.append(
                SolutionEntry(
                    comb[0] + 1,
                    comb[1],
                    comb[2],
                    comb[3],
                    int(x[n]),
                )
            )
        return actions

    @override
    def _evaluate(self, x: NDArray[np.float64], out: dict[str, NDArray[np.float64]]):
        n_individuals = x.shape[0]
        f = np.zeros((n_individuals, 1))  # Shape: (n_individuals, n_objectives)

        for i in range(n_individuals):
            actions = self.decode_actions(x[i])
            evaluator = Evaluator(
                actions, self.demand, SERVER_MAP, DATACENTER_MAP, SELLING_PRICES_MAP
            )
            f[i, 0] = -evaluator.get_score()  # Negative because we're minimizing

        out["F"] = f


if __name__ == "__main__":
    algorithm = NSGA2(
        pop_size=100,
        eliminate_duplicates=True,
    )
    np.random.seed(2281)
    demand = get_demand()
    problem = MyProblem(demand)
    res: None | Any = minimize(problem, algorithm, termination=("n_gen", 100))  # type: ignore[reportUnknownVariableType]
    if res is None:
        print("No solution found")
        exit()
    best_solution = problem.decode_actions(res.X[0])  # type: ignore[reportUnknownArgumentType]
    best_score = Evaluator(
        best_solution, demand, SERVER_MAP, DATACENTER_MAP, SELLING_PRICES_MAP
    ).get_score()
    print(f"Best score: {best_score}")
