# pyright: reportAssignmentType=false, reportUnknownMemberType=false


import numpy as np
import pandas as pd

from constants import get_datacenters, get_selling_prices, get_servers
from evaluation import get_actual_demand
from seeds import known_seeds
from solver.models import Demand
from solver.sat import solve

# from utils import save_solution

seeds: list[int] = known_seeds("training")

for seed in seeds:
    # SET THE RANDOM SEED
    np.random.seed(seed)

    # GET THE DEMAND
    parsed_demand: list[Demand] = []
    for i, row in get_actual_demand(pd.read_csv("./data/demand.csv")).iterrows():  # type: ignore[reportUnknownVariableType, reportArgumentType]
        parsed_demand.append(
            Demand(row.time_step, row.server_generation, row.high, row.medium, row.low).setup()  # type: ignore[reportUnknownArgumentType]
        )
    solve(parsed_demand, get_datacenters(), get_selling_prices(), get_servers())
    break

    # CALL YOUR APPROACH HERE
    # solution = get_my_solution(actual_demand)
    #
    # # SAVE YOUR SOLUTION
    # save_solution(solution, f"./output/{seed}.json")
