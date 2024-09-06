from pymoo.core.problem import Problem

import numpy as np


class DailyElementWiseProblem(Problem):
    def __init__(self, 
                    demand_vector, 
                    selling_price, 
                    server_tracker, 
                    current_day, 
                    purchase_price, 
                    maintenance_cost,
                    energy_cost):
        
        current_x = server_tracker.map_servers_to_search_space()
        offset = np.sum(current_x)
        self.options = np.arange(-offset, 55846-offset, 2)
        n_var = 21

        boundaries = server_tracker.define_restrictions(current_x);
        xl = np.array(boundaries[0], dtype=int)
        xu = np.array(boundaries[1], dtype=int)
        print(f"Lower Bound: {xl}")
        print(f"Upper Bound: {xu}")

        self.demand_vector = np.array(demand_vector)
        self.selling_price = np.array(selling_price)
        self.server_tracker = server_tracker
        self.current_day = current_day
        self.purchase_price = purchase_price
        self.maintenance_cost = maintenance_cost
        self.energy_costs = energy_cost
        self.group_sums = [25245, 15300, 15300]

        super().__init__(n_var=n_var, n_obj=3, n_ieq_constr=3, xl=xl, xu=xu, type_var=int)

    def alpha(self, days):
        # Identity function for now
        return days
    
    def cost_function(self, x_i):
        # logic: consider our argument and then consider all other servers then sum. 
        # essentially, we abstract the sum as cost(x_i) + CONSTANT where CONSTANT is the price of all previous
        # servers
        total_cost = 0
        for i in range(self.current_day):
            for j in range(21):
                sb = self.server_tracker.servers[i][j] # sb stands for server_batch
                total_cost += self.maintenance_cost[j]*sb + sb*self.alpha(self.current_day - i + 1)

        return total_cost
    
    def calculate_lifespan(self, x_i):
        # logic: all the days active and then divide the value by 96*the number of the fleet

        total_value = 0
        fleet_size = np.sum(self.server_tracker.map_servers_to_search_space())
        for i in range(self.current_day):
            total_value += (i+1)*np.sum(self.server_tracker.servers[i])
        
        total_value += sum(np.sum(row) for row in x_i)
        
        return (total_value // (fleet_size * 96)) if fleet_size > 0 else 1


    def _evaluate(self, x, out, *args, **kwargs):
        values = self.options[x.astype(int)]
        current_values = np.array(self.server_tracker.map_servers_to_search_space())
        
        # Ensure values and current_values have compatible shapes
        if len(values.shape) == 2:
            current_values = current_values.reshape(1, -1)
        
        new_values = np.maximum(values - current_values, 0)

        total_values = current_values + new_values

        # Calculate the objective function
        part1 = np.sum(np.minimum(total_values, self.demand_vector) * self.selling_price, axis=1)
        epsilon = 1e-10
        part2 = np.sum(np.minimum(total_values, self.demand_vector) / (total_values + epsilon), axis=1)

        cost = np.array([self.cost_function(x_i) for x_i in x])

        lifespan = np.array([self.calculate_lifespan(x_i) for x_i in x])

        out["F"] = np.column_stack((-(part1 * part2).reshape(-1, 1), cost, lifespan)) 

        # Inequality constraints: group sums should be less than or equal to the specified values
        out["G"] = np.column_stack([
            np.sum(total_values[:, :7], axis=1) - self.group_sums[0],
            np.sum(total_values[:, 7:14], axis=1) - self.group_sums[1],
            np.sum(total_values[:, 14:], axis=1) - self.group_sums[2]
        ])

        out["new_values"] = new_values
        out["total_values"] = total_values

        return out