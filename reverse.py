import json

from constants import get_datacenters
from solver.models import Action, ServerGeneration, SolutionEntry

# from utils import save_solution  #. type: ignore[import]


def get_solution():

    data: list[dict[str, int | str]] = json.load(open("output/1741.json"))

    aggregate: dict[int, dict[str, dict[ServerGeneration, int]]] = {
        ts: {
            dc.datacenter_id: {gen: 0 for gen in ServerGeneration}
            for dc in get_datacenters()
        }
        for ts in range(1, 168)
    }

    for entry in data:
        aggregate[int(entry["time_step"])][str(entry["datacenter_id"])][
            ServerGeneration(entry["server_generation"])
        ] += 1

    solutions: list[SolutionEntry] = []

    for ts in aggregate:
        for dc in aggregate[ts]:
            for gen in aggregate[ts][dc]:
                count = aggregate[ts][dc][gen]
                if count == 0:
                    continue
                solutions.append(SolutionEntry(ts, dc, gen, Action.BUY, count))
    return solutions


if __name__ == "__main__":
    solutions = get_solution()
    for entry in solutions:
        print(
            f"{entry.timestep} {entry.datacenter_id} {entry.server_generation} {entry.amount}"
        )
