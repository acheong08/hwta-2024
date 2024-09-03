# pyright: basic

import json
import subprocess

from evaluation import evaluation_function
from utils import load_problem_data, load_solution


def get_score(f: str, seed: int, verbose: bool = False) -> float:
    solution_scores: dict[str, float] = json.load(open("solution_scores.json", "r"))
    md5sum = subprocess.run(
        ["md5sum", f], stdout=subprocess.PIPE, text=True
    ).stdout.split()[0]
    if not verbose:
        if md5sum in solution_scores:
            return solution_scores[md5sum]
    solution = load_solution(f)
    demand, datacenters, servers, selling_prices = load_problem_data()
    score: int = evaluation_function(  # type: ignore[]
        solution,
        demand,
        datacenters,
        servers,
        selling_prices,
        seed=seed,
        verbose=verbose,
    )
    solution_scores[md5sum] = score
    json.dump(solution_scores, open("solution_scores.json", "w"))
    return score
