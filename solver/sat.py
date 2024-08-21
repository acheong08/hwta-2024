# pyright: reportAssignmentType=false


from ortools.sat.python import cp_model

from .debuggy import debug_on  # pyright: ignore[reportUnknownVariableType]
from .models import (Datacenter, Demand, SellingPrices, Sensitivity, Server,
                     ServerGeneration)

# t = "timestep"
# d = "datacenter"
# s = "server_generation"
# a = "actions"
# am = "amount"
actions = ["buy", "sell"]

INFINITY = 100_000_000_00


@debug_on(KeyError)
def solve(
    demands: list[Demand],
    datacenters: list[Datacenter],
    selling_prices: list[SellingPrices],
    servers: list[Server],
) -> None:

    cp = cp_model.CpModel()
    """
    The action model is what will be solved by SAT. It decides when to buy, sell, or move servers.
    """
    action_model = {
        timestep: {
            datacenter.datacenter_id: {
                server_generation: {
                    action: cp.new_int_var(
                        0,
                        INFINITY,
                        f"{timestep}_{datacenter}_{server_generation}_{action}_action",
                    )
                    for action in actions
                }
                for server_generation in ServerGeneration
            }
            for datacenter in datacenters
        }
        for timestep in range(1, max(demand.time_step for demand in demands) + 1)
    }
    # action_model[0] = {
    #     dc.datacenter_id: {
    #         sg: {ac: cp.new_int_var(0, 0, f"0_{dc}_{sg}_{ac}_action") for ac in actions}
    #         for sg in ServerGeneration
    #     }
    #     for dc in datacenters
    # }
    # Allow quick lookups of id to object
    sg_map = {server.server_generation: server for server in servers}

    # We calculate the total cost of buying servers by multiplying to volume to price
    buying_cost = cp.new_int_var(0, INFINITY, "cost")
    _ = cp.add(
        buying_cost
        == sum(
            action_model[t][d][s]["buy"] * sg_map[s].purchase_price
            for t in action_model
            for d in action_model[t]
            for s in action_model[t][d]
        )
    )

    # Only one action (or less) can be taken per datacenter per timestep
    for ts in action_model:
        if ts == 0:
            continue
        for dc in action_model[ts]:
            for action in actions:
                for server_gen in action_model[ts][dc]:
                    cur_mod = cp.new_int_var(0, 1, f"{ts}_{dc}_{action}")
                    _ = cp.add_modulo_equality(
                        cur_mod, action_model[ts][dc][server_gen][action], 2
                    )
                    for other_action in actions:
                        if other_action != action:
                            ot_mod = cp.new_int_var(
                                0, 1, f"{ts}_{dc}_{action}_{other_action}"
                            )
                            _ = cp.add_modulo_equality(
                                ot_mod,
                                action_model[ts][dc][server_gen][other_action],
                                2,
                            )
                            _ = cp.add(cur_mod == 0).only_enforce_if(
                                ot_mod.is_equal_to(1)
                            )

    # Now we need to calculate the total availability of each type of server at each timestep
    # based on the sum of purchase amounts minus the sum of sell amounts
    # Customers don't really care about cost of energy and stuff like that. We can deal with that later
    availability = {
        t: {
            sg: {
                dc.datacenter_id: cp.new_int_var(0, INFINITY, f"{t}_{sg}_{dc}_avail")
                for dc in datacenters
            }
            for sg in ServerGeneration
        }
        for t in action_model
    }
    # HACK
    availability[0] = {
        sg: {
            dc.datacenter_id: cp.new_int_var(0, 0, f"0_{sg}_{dc}_avail")
            for dc in datacenters
        }
        for sg in ServerGeneration
    }
    for ts in availability:
        if ts == 0:
            continue
        for server_generation in availability[ts]:
            for dc in availability[ts][server_generation]:
                # Logic: we sum buy/sells for datacenters that match the sensitivity and subtract the sells
                # We do this for all timesteps in the past
                _ = cp.add(
                    # Calculate current sum
                    availability[ts][server_generation][dc]
                    == sum(
                        (action_model[ts][dc][server_generation]["buy"])
                        for dc in action_model[ts]
                    )
                    - sum(
                        (action_model[ts][dc][server_generation]["sell"])
                        for dc in action_model[ts]
                    )
                    # Take the previous timestep
                    + availability[ts - 1][server_generation][dc]
                )
    for ts in availability:
        if ts == 0:
            continue
        for server_generation in availability[ts]:
            for dc in availability[ts][server_generation]:
                # You can't sell more than you have
                _ = cp.add(
                    availability[ts][server_generation][dc]
                    >= action_model[ts][dc][server_generation]["sell"]
                )
    dc_map = {dc.datacenter_id: dc for dc in datacenters}
    energy_cost = cp.new_int_var(0, INFINITY, "energy_cost")
    _ = cp.add(
        energy_cost
        == sum(
            availability[ts][sg][dc]
            * sg_map[sg].energy_consumption
            * dc_map[dc].cost_of_energy
            for ts in availability
            for sg in availability[ts]
            for dc in availability[ts][sg]
        )
    )

    maintenance_cost = cp.new_int_var(0, INFINITY, "maintenance_cost")
    _ = cp.add(
        maintenance_cost
        == sum(
            availability[ts][sg][dc] * sg_map[sg].average_maintenance_fee
            for ts in availability
            for sg in availability[ts]
            for dc in availability[ts][sg]
        )
    )

    # Ensure we don't run out of slots on datacenters
    for ts in availability:
        if ts == 0:
            continue
        for dc in datacenters:
            _ = cp.add(
                sum(
                    availability[ts][sg][dc.datacenter_id] * sg_map[sg].slots_size
                    for sg in availability[ts]
                )
                <= dc_map[dc.datacenter_id].slots_capacity
            )

    demand_map: dict[int, dict[ServerGeneration, dict[Sensitivity, int]]] = {}
    for demand in demands:
        if demand_map.get(demand.time_step) is None:
            demand_map[demand.time_step] = {}
        if demand_map[demand.time_step].get(demand.server_generation) is None:
            demand_map[demand.time_step][demand.server_generation] = {}
        for sen in Sensitivity:
            demand_map[demand.time_step][demand.server_generation][sen] = (
                demand.get_latency(sen)
            )
    # Calculate server utilization
    # This is the ratio of demand to availability for server type (sensitivity + server generation)
    revenues = {
        ts: {
            sg: {
                sen: cp.new_int_var(0, INFINITY* 100, f"{ts}_{sg}_{sen}_util")
                for sen in Sensitivity
            }
            for sg in ServerGeneration
        }
        for ts in availability
    }
    revenues[0] = {
        sg: {sen: cp.new_int_var(0, 0, f"0_{sg}_{sen}_util") for sen in Sensitivity}
        for sg in ServerGeneration
    }
    sp_map: dict[ServerGeneration, dict[Sensitivity, int]] = {}
    for sp in selling_prices:
        if sp_map.get(sp.server_generation) is None:
            sp_map[sp.server_generation] = {}

        sp_map[sp.server_generation][sp.latency_sensitivity] = sp.selling_price

    for ts in revenues:
        if ts == 0:
            continue

        for sg in revenues[ts]:
            for sen in revenues[ts][sg]:
                total_availability = sum(
                    (
                        availability[ts][sg][dc.datacenter_id]
                        if dc.latency_sensitivity == sen
                        else 0
                    )
                    for dc in datacenters
                )
                demand = cp.new_constant(demand_map[ts].get(sg, {sen: 0})[sen])
                # Get amount of demand that can be satisfied
                m = cp.new_int_var(0, INFINITY, f"{ts}_{sg}_{sen}_m")
                _ = cp.add_min_equality(m, [demand, total_availability])
                _ = cp.add(revenues[ts][sg][sen] == m * sp_map[sg][sen])

    total_cost = cp.new_int_var(0, INFINITY, "total_cost")
    _ = cp.add(total_cost == buying_cost + energy_cost + maintenance_cost)
    _ = cp.maximize(
        sum(
            revenues[ts][sg][sen]
            for ts in revenues
            for sg in revenues[ts]
            for sen in revenues[ts][sg]
        )
        - total_cost
    )

    total_revenue = sum(
        revenues[ts][sg][sen]
        for ts in revenues
        for sg in revenues[ts]
        for sen in revenues[ts][sg]
    )
    solver = cp_model.CpSolver()
    status = solver.solve(cp)
    if (
        status == cp_model.OPTIMAL  # type: ignore[reportUnnecessaryComparison]
        or status == cp_model.FEASIBLE  # type: ignore[reportUnnecessaryComparison]
    ):
        print(solver.solution_info())
        print(solver.response_stats())
        for ts in action_model:
            for dc in action_model[ts]:
                for sg in action_model[ts][dc]:
                    for action in action_model[ts][dc][sg]:
                        if solver.value(action_model[ts][dc][sg][action]) > 0:
                            print(
                                f"{ts} {dc} {sg} {action} {solver.value(action_model[ts][dc][sg][action])}"
                            )
        print("Revenue:", solver.value(total_revenue))
        print("Cost:", solver.value(total_cost))
        print("Profit:", solver.value(total_revenue) - solver.value(total_cost))
        print("Energy Cost:", solver.value(energy_cost))
        print("Maintenance Cost:", solver.value(maintenance_cost))
        print("Buying Cost:", solver.value(buying_cost))
        breakpoint()
    elif status == cp_model.INFEASIBLE:  # type: ignore[reportUnnecessaryComparison]
        print("Infeasible")
    elif status == cp_model.MODEL_INVALID:  # type: ignore[reportUnnecessaryComparison]
        print("Model Invalid")
        print(solver.response_stats())
