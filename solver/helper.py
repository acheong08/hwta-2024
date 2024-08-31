from solver.models import (
    Action,
    Datacenter,
    Demand,
    SellingPrices,
    Sensitivity,
    Server,
    ServerGeneration,
    SolutionEntry,
)

import numpy as np

KEYS = [ServerGeneration.CPU_S1, ServerGeneration.CPU_S2, ServerGeneration.CPU_S3 , ServerGeneration.CPU_S4,
           ServerGeneration.GPU_S1, ServerGeneration.GPU_S2, ServerGeneration.GPU_S3]

def mapDemandToVector(demand : dict) -> np.ndarray:
    
    
    vector = []
    for key in KEYS:
        if demand.get(key) == None:
            vector.extend([0,0,0])
        else:
            for x in reversed(demand[key]):
                vector.append(demand[key][x])
    
    return np.array(vector)
            
def mapSellingPriceToVector(selling_price : dict) -> np.ndarray:
    
    vector = []
    print(len(selling_price))
    for item in selling_price:
        vector.append(item.selling_price)
        
    return np.array(vector)