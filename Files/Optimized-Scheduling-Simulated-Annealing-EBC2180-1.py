import math
import random
import time

# -- 1. Setting up Global Constraints -- #

HQ_NODE    = 251
N_STUDENTS = 20

# Convert all time data into seconds

MAX_SHIFT  = 8 * 3600
COST_S     = 60.0 / 3600.0

# Interval controls for easy tweaking of the model

DEBUG_INTERVAL  = 3.0
SAVE_INTERVAL   = 5.0
REHEAT_INTERVAL = 10.0
REHEAT_RATE = 0.5
SANITY_CHECK_MODE = False

# -- 2. Data Loading -- #

# Load the driving times as a matrix (list of list), indexed in O(1)
def load_drive(path):
    drive = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                drive.append(list(map(int, line.split())))
    return drive

# Load the order.txt to get all important variables (orderID, Node, Duration, profits) as list and skills as matrix, indexed in O(1)

def load_orders(path):
    orderID, nodes, durations, profits, skills = [], [], [], [], []
    with open(path) as fh:

        # Skip the first line containing headers
        fh.readline()
        for line in fh:
            line = line.strip()
            if not line:
                continue

            # Split by tab as per your file format
            tok = line.split('\t')
            
            # Updated variables based on set columns
            orderID.append(int(tok[0]))
            nodes.append(int(tok[2]))
            durations.append(int(tok[5]) * 60)
            profits.append(float(tok[6]))
            
            # Student skills put in a matrix format
            flags = [int(x) for x in tok[7: 7 + N_STUDENTS]]
            skills.append([s for s, v in enumerate(flags) if v == 1])
            
    return orderID, nodes, durations, profits, skills

# -- 3. Delta Time Helper Formulas (Δprofit = Δrevenue − COST_S × Δtime) -- #

def delta_time_insert(route, position, order, nodes, durations, drive):

    # Conditional logic, if position = 0 then previous stop was HQ & if position = end then next stop is HQ
    A = HQ_NODE if position == 0 else nodes[route[position - 1]]
    B = HQ_NODE if position == len(route) else nodes[route[position]]
    
    order_node = nodes[order]

    # Delta Time = Drive from node A (previous) to inserted order + order length + drive from order to node B (next) - drive A to B
    return drive[A][order_node] + durations[order] + drive[order_node][B] - drive[A][B]

def dt_remove(route, position, order, nodes, durations, drive):
    order_node = nodes[order]

    # Same conditional logic to check for HQ_NODE
    A = HQ_NODE if position == 0 else nodes[route[position - 1]]
    B = HQ_NODE if position == len(route) - 1 else nodes[route[position + 1]]

    # Delta time is the reduced driving times - now skipped order time + drive A to B
    return drive[A][B] - drive[A][order_node] - durations[order] - drive[order_node][B]

def dt_2opt(route, i, j, nodes, drive):

    # Contitional logic to check for HQ nodes
    A = HQ_NODE if i == 0 else nodes[route[i - 1]]
    B = HQ_NODE if j == len(route) - 1 else nodes[route[j + 1]]

    # Node i and Node J which are swapping order
    node_i = nodes[route[i]]
    node_j = nodes[route[j]]

    # Remember driving times are symetric so only the edge cases differ, delta time just swappes edge cases
    return drive[A][node_j] + drive[node_i][B] - drive[A][node_i] - drive[node_j][B]

# Create a delta time for insert after removal, this is usefull for swap and same student relocate feature, reduces the operations closer O(1) 
def dt_insert_after_removal(route, remove_pos, insert_pos, order, nodes, durations, drive):
    order_node = nodes[order]
    n = len(route)

    # After popping remove_pos, indices >= remove_pos shift left by 1.
    # So to get the neighbors of insert_pos in the post-removal route,
    # we translate insert_pos back to original-route coordinates.
    if insert_pos <= remove_pos:
        # Insert is to the left of (or at) the removal — no shift needed.
        A = HQ_NODE if insert_pos == 0 else nodes[route[insert_pos - 1]]
        B = nodes[route[insert_pos]] if insert_pos < n else HQ_NODE
        # But if insert_pos == remove_pos, B is the node being removed —
        # we want X's right neighbor instead.
        if insert_pos == remove_pos:
            B = HQ_NODE if remove_pos == n - 1 else nodes[route[remove_pos + 1]]
    else:
        # insert_pos is in the right half — it refers to the post-removal route,
        # so original index is insert_pos + 1 (shift back).
        real_left  = insert_pos       # in original route (= insert_pos after shift)
        real_right = insert_pos + 1   # in original route
        A = nodes[route[real_left]]
        B = HQ_NODE if real_right >= n else nodes[route[real_right]]

    return drive[A][order_node] + durations[order] + drive[order_node][B] - drive[A][B]

# -- 4. Solution Class -- #

class solutions:

    # Set the following attributes for the class, routes, route time, route profit, assigned orders, unassigned orders and profit

    __slots__ = ('routes', 'route_time', 'route_profit', 'assigned_orders', 'unassigned_orders', 'profit')

    # Initialize the attribute as list accordingly
    def __init__(self, n_orders):
        self.routes = [[] for _ in range(N_STUDENTS)]
        self.route_time = [0.0] * N_STUDENTS
        self.route_profit = [0.0] * N_STUDENTS
        self.assigned_orders = [-1] * n_orders
        self.unassigned_orders = list(range(n_orders))
        self.profit = 0.0

    # Define the number of customers as the length of all routes combined
    def n_customers(self):
        return sum(len(route) for route in self.routes)
    
    # Use python __new__ to copy all important lists, this is a faster method than deepcopying everything
    def clone(self):
        clone = solutions.__new__(solutions)
        clone.routes = [list(r) for r in self.routes]
        clone.route_time = list(self.route_time)
        clone.route_profit = list(self.route_profit)
        clone.assigned_orders = list(self.assigned_orders)
        clone.unassigned_orders = list(self.unassigned_orders)
        clone.profit = self.profit
        return clone
    
    # Create a function to recompute the profit, we do this every X iterations to remove float point drift
    def recompute_profit(self):

        #Loop profit operations for all students
        total = sum(
            self.route_profit[s] - COST_S * self.route_time[s]
            for s in range(N_STUDENTS) if self.routes[s]
        )
        self.profit = total
        return total
    
    # Write solution in the required output format
    def write(self, path, order_ids):
        with open(path, 'w') as fh:
            fh.write(f"{int(self.profit)}\n")
            for s in range(N_STUDENTS):
                fh.write(f"{len(self.routes[s])}\n")
                for o in self.routes[s]:
                    fh.write(f"{order_ids[o]}\n")
    
# -- 5. Neighbourhood operators -- #    

# Defining the operation ADD, this is greedy since it tries all locations for all students, but this will greatly improve our initial search space
def op_add(sol, nodes, durations, profits, skills, drive):

    # Check if there are unassigned orders left
    if not sol.unassigned_orders:
        return None

    # Pick a random order from the unassigned list
    unassigned_index = random.randrange(len(sol.unassigned_orders))
    order_index = sol.unassigned_orders[unassigned_index]
    
    # Get the list of students eligible to perform this specific order
    eligible_students = skills[order_index]
    
    if not eligible_students:
        return None

    best_delta_profit = None
    best_student = -1
    best_position = -1
    best_delta_time = 0.0

    # Exhaustive search for the best insertion point across all eligible students
    for student_index in eligible_students:
        current_route = sol.routes[student_index]
        
        # Iterate through every possible insertion gap (including start and end)
        for position in range(len(current_route) + 1):
            delta_time = delta_time_insert(
                current_route, position, order_index, nodes, durations, drive
            )
            
            # Constraint Check: Ensure the student does not exceed the 8-hour shift
            if sol.route_time[student_index] + delta_time > MAX_SHIFT:
                continue
            
            # Calculate Delta Profit: Revenue - (Cost per second * Additional time)
            delta_profit = profits[order_index] - (COST_S * delta_time)
            
            # Track the best possible insertion (highest delta profit)
            if best_delta_profit is None or delta_profit > best_delta_profit:
                best_delta_profit = delta_profit
                best_student = student_index
                best_position = position
                best_delta_time = delta_time

    # If no feasible insertion was found return None
    if best_student < 0:
        return None

    # Apply within the function since we decide later whether to accept the change with temperature
    def apply():

        # Update the student's specific route and metrics
        sol.routes[best_student].insert(best_position, order_index)
        sol.route_time[best_student]   += best_delta_time
        sol.route_profit[best_student] += profits[order_index]
        
        # Update global solution state
        sol.assigned_orders[order_index] = best_student
        
        # O(1) removal from unassigned_orders list using swap-to-back
        sol.unassigned_orders[unassigned_index] = sol.unassigned_orders[-1]
        sol.unassigned_orders.pop()
        
        # Update the total solution profit
        sol.profit += best_delta_profit

    return best_delta_profit, apply

def op_add_non_greedy(sol, nodes, durations, profits, skills, drive):
    if not sol.unassigned_orders:
        return None

    unassigned_index = random.randrange(len(sol.unassigned_orders))
    order_index = sol.unassigned_orders[unassigned_index]
    
    #Use the list already created by load_orders
    eligible_students = skills[order_index]
    
    if not eligible_students:
        return None
    
    student_index = random.choice(eligible_students)
    current_route = sol.routes[student_index]
    
    # Correctly allows insertion at any gap
    position = random.randrange(len(current_route) + 1)

    delta_time = delta_time_insert(current_route, position, order_index, nodes, durations, drive)

    # 8-hour shift constraint (28800 seconds)
    if sol.route_time[student_index] + delta_time > MAX_SHIFT: # Use global constant
        return None

    delta_profit = profits[order_index] - (COST_S * delta_time)

    def apply():
        sol.routes[student_index].insert(position, order_index)
        sol.route_time[student_index]   += delta_time
        sol.route_profit[student_index] += profits[order_index]
        
        sol.assigned_orders[order_index] = student_index
        
        # O(1) removal using swap-to-back
        sol.unassigned_orders[unassigned_index] = sol.unassigned_orders[-1]
        sol.unassigned_orders.pop()
        
        sol.profit += delta_profit

    return delta_profit, apply

# The remove operator, takes a random assigned order out of its route.
def op_remove(sol, nodes, durations, profits, drive):

    #Find all students who currently have at least one order assigned
    active_students = [s for s in range(N_STUDENTS) if sol.routes[s]]
    
    if not active_students:
        return None

    #Pick a random student and a random position in their route
    student_index = random.choice(active_students)
    current_route = sol.routes[student_index]
    position = random.randrange(len(current_route))
    
    #Identify the order to be removed
    order_index = current_route[position]
    
    #Calculate time saved (dt_remove returns a negative value)
    delta_time = dt_remove(current_route, position, order_index, nodes, durations, drive)
    
    #Since delta_time is negative, -COST_S * delta_time is the positive money saved.
    delta_profit = (-COST_S * delta_time) - profits[order_index]

    # Apply within the function since we decide later whether to accept the change with temperature
    def apply():
        # Remove the order from the student's route
        sol.routes[student_index].pop(position)
        
        # Update student's specific metrics
        sol.route_time[student_index]   += delta_time
        sol.route_profit[student_index] -= profits[order_index]
        
        # Safety: If route is now empty, ensure metrics are exactly zero
        if not sol.routes[student_index]:
            sol.route_time[student_index]   = 0.0
            sol.route_profit[student_index] = 0.0
        
        # Update global solution state
        sol.assigned_orders[order_index] = -1
        sol.unassigned_orders.append(order_index)
        
        # Update the overall solution profit
        sol.profit += delta_profit

    return delta_profit, apply

# Two opt operator, reverse a random sub-segment of one student's route, great for untanegling routes
def op_2opt(sol, nodes, durations, drive):

    # Only pick students who have at least 2 orders (minimum needed to reverse)
    active_students = [s for s in range(N_STUDENTS) if len(sol.routes[s]) >= 2]
    
    if not active_students:
        return None
    
    # pick random student
    student_index = random.choice(active_students)
    current_route = sol.routes[student_index]
    n = len(current_route)
    
    # Pick two random points to define the segment to reverse
    i = random.randrange(n - 1)
    j = random.randrange(i + 1, n)

    # Calculate the change in driving time (dt_2opt logic we fixed earlier)
    delta_time = dt_2opt(current_route, i, j, nodes, drive)
    
    # Check if this reversal violates the 8-hour shift constraint
    if sol.route_time[student_index] + delta_time > MAX_SHIFT:
        return None

    # Delta Profit = -Cost of the change in time (Revenue remains unchanged)
    delta_profit = -COST_S * delta_time

    def apply():
        # Reverse the segment in-place
        current_route[i : j + 1] = current_route[i : j + 1][::-1]
        
        # Update metrics
        sol.route_time[student_index] += delta_time
        sol.profit += delta_profit

    return delta_profit, apply

# Moves an order from its current route to a random position in a random eligible student's route
def op_relocate(sol, nodes, durations, profits, skills, drive):
    active_students = [s for s in range(N_STUDENTS) if sol.routes[s]]
    if not active_students: return None

    source_student = random.choice(active_students)
    source_route = sol.routes[source_student]
    source_pos = random.randrange(len(source_route))
    order_index = source_route[source_pos]
    
    dt_rem = dt_remove(source_route, source_pos, order_index, nodes, durations, drive)
    
    eligible_students = skills[order_index]
    target_student = random.choice(eligible_students)
    
    # Determine the number of available gaps after removal
    if target_student == source_student:
        max_gaps = len(source_route) # After popping 1, there are (N-1)+1 gaps
    else:
        max_gaps = len(sol.routes[target_student]) + 1

    target_pos = random.randrange(max_gaps)

    # Avoid no-ops
    if target_student == source_student and target_pos == source_pos:
        return None

    # Calculate delta 
    if target_student == source_student:
        dt_ins = dt_insert_after_removal(source_route, source_pos, target_pos, order_index, nodes, durations, drive)
    else:
        dt_ins = delta_time_insert(sol.routes[target_student], target_pos, order_index, nodes, durations, drive)

    if ( (sol.route_time[target_student] + (dt_rem if source_student == target_student else 0) + dt_ins) > MAX_SHIFT ):
        return None

    total_delta_profit = -COST_S * (dt_rem + dt_ins)

    def apply():
        # Removing from source
        order = sol.routes[source_student].pop(source_pos)
        sol.route_time[source_student] += dt_rem
        sol.route_profit[source_student] -= profits[order_index]
        
        # Cleanup source if empty
        if not sol.routes[source_student]:
            sol.route_time[source_student] = 0.0
            sol.route_profit[source_student] = 0.0

        # Insert into target (target_pos is now the absolute correct index)
        sol.routes[target_student].insert(target_pos, order)
        sol.route_time[target_student] += dt_ins
        sol.route_profit[target_student] += profits[order_index]
        
        sol.assigned_orders[order_index] = target_student
        sol.profit += total_delta_profit

    return total_delta_profit, apply

# Swap operator, swaps order between two student routes - random location for now

def op_swap(sol, nodes, durations, profits, skills, drive):
    # Selection: Pick two different students who both have at least one order
    active_students = [s for s in range(N_STUDENTS) if sol.routes[s]]
    if len(active_students) < 2:
        return None

    studentA, studentB = random.sample(active_students, 2)
    
    # Pick a random order from each student's route
    A_route = sol.routes[studentA]
    B_route = sol.routes[studentB]
    A_pos = random.randrange(len(A_route))
    B_pos = random.randrange(len(B_route))

    # Create random position where new orders will be inserted.
    # Since we will pop an order first, the remaining route length will be len() - 1.
    # A list of size N-1 has N valid insertion gaps (0 to N-1 inclusive).
    insert_A_pos = random.randrange(len(A_route))
    insert_B_pos = random.randrange(len(B_route))
    
    orderA = A_route[A_pos]
    orderB = B_route[B_pos]

    if studentA not in skills[orderB] or studentB not in skills[orderA]:
        return None

    # Delta time evaluation for Student A
    dt_A_rem = dt_remove(A_route, A_pos, orderA, nodes, durations, drive)
    dt_A_ins = dt_insert_after_removal(A_route, A_pos, insert_A_pos, orderB, nodes, durations, drive)
    dt_A = dt_A_rem + dt_A_ins

    # Delta time evaluation for Student B
    dt_B_rem = dt_remove(B_route, B_pos, orderB, nodes, durations, drive)
    dt_B_ins = dt_insert_after_removal(B_route, B_pos, insert_B_pos, orderA, nodes, durations, drive)
    dt_B = dt_B_rem + dt_B_ins

    # Constraint Check: Both students must stay under the 8-hour shift
    if (sol.route_time[studentA] + dt_A > MAX_SHIFT or 
        sol.route_time[studentB] + dt_B > MAX_SHIFT):
        return None

    # Profit Calculation
    # Note: Global revenue doesn't change because the two orders are just trading places.
    # Therefore, the total global profit change is purely driven by the change in driving time.
    total_delta_profit = -COST_S * (dt_A + dt_B)

    def apply():
        # Update Student A (Remove orderA, then insert orderB)
        sol.routes[studentA].pop(A_pos)
        sol.routes[studentA].insert(insert_A_pos, orderB)
        sol.route_time[studentA] += dt_A
        sol.route_profit[studentA] += (profits[orderB] - profits[orderA])
        sol.assigned_orders[orderB] = studentA

        # Update Student B (Remove orderB, then insert orderA)
        sol.routes[studentB].pop(B_pos)
        sol.routes[studentB].insert(insert_B_pos, orderA)
        sol.route_time[studentB] += dt_B
        sol.route_profit[studentB] += (profits[orderA] - profits[orderB])
        sol.assigned_orders[orderA] = studentB

        # Update Global Profit
        sol.profit += total_delta_profit

    return total_delta_profit, apply

# -- 6. Greedy initialization -- #

# Define an initilisation that makes the greedy choice, Orders are processed by 'profit density' (profit per second).
def greedy_initialization(nodes, durations, profits, skills, drive):

    n_orders = len(nodes)
    sol = solutions(n_orders)

    # Sort orders by profit-density (descending)
    # Using max(d, 1) to avoid division by zero if an order has 0 duration
    order_sequence = sorted(
        range(n_orders),
        key=lambda o: profits[o] / max(durations[o], 1),
        reverse=True
    )

    # Iterate through sorted orders and find the best insertion point
    for order_index in order_sequence:
        best_delta_profit = 0.0
        best_student = -1
        best_position = -1
        best_delta_time = 0.0

        # Check every student eligible for this order
        for student_index in skills[order_index]:
            current_route = sol.routes[student_index]
            
            for position in range(len(current_route) + 1):
                delta_time = delta_time_insert(
                    current_route, position, order_index, nodes, durations, drive
                )
                
                # Check 8-hour shift constraint
                if sol.route_time[student_index] + delta_time > MAX_SHIFT:
                    continue
                
                # Delta Profit = Revenue - (Cost per second * Additional time)
                delta_profit = profits[order_index] - (COST_S * delta_time)
                
                if delta_profit > best_delta_profit:
                    best_delta_profit = delta_profit
                    best_student = student_index
                    best_position = position
                    best_delta_time = delta_time

        # If a profitable insertion was found, apply it
        if best_student >= 0:
            sol.routes[best_student].insert(best_position, order_index)
            sol.route_time[best_student]   += best_delta_time
            sol.route_profit[best_student] += profits[order_index]
            sol.assigned_orders[order_index] = best_student
            
            # Remove from unassigned list
            # Since this runs once, O(n) index search is fine
            idx = sol.unassigned_orders.index(order_index)
            sol.unassigned_orders[idx] = sol.unassigned_orders[-1]
            sol.unassigned_orders.pop()

    # Final profit sync
    sol.recompute_profit()
    return sol

# -- 6.5 Dynamic Weighting system -- #

# Ended up with static weights since any dynamic weighting system could NOT beat the static weight system
def update_operator_weights(temp):

    w_relocate = 0.35
    w_2opt = 0.20
    w_add = 0.30
    w_remove   = 0.15
    w_swap = 0.10
    
    total = w_relocate + w_2opt + w_add + w_remove + w_swap
    probs = [w_relocate/total, w_2opt/total, w_add/total, w_remove/total, w_swap/total]
    
    cumulative = []
    acc = 0.0
    for p in probs:
        acc += p
        cumulative.append(acc)
    return cumulative

# -- 7. The Simulated Annealing Loop --
def run_simulated_annealing(order_ids, nodes, durations, profits, skills, drive_matrix, time_limit=300):

    # Start with the greedy_initialization
    print("=== Building greedy initial solution ===")
    current_solution = greedy_initialization(nodes, durations, profits, skills, drive_matrix)
    best_solution = current_solution.clone()
    print(f"Greedy Init: profit=€{current_solution.profit:.2f} | orders={current_solution.n_customers()}\n")

    # Set the operator functions
    operator_functions = [
        lambda sol: op_relocate(sol, nodes, durations, profits, skills, drive_matrix),
        lambda sol: op_2opt(sol, nodes, durations, drive_matrix),
        lambda sol: op_add_non_greedy(sol, nodes, durations, profits, skills, drive_matrix),
        lambda sol: op_remove(sol, nodes, durations, profits, drive_matrix),
        lambda sol: op_swap(sol, nodes, durations, profits, skills, drive_matrix)
    ]

    # Simulated Annealing Parameters
    initial_temperature = 12.5
    cooling_rate = 0.99999997
    current_temperature = initial_temperature
    minimum_temperature = 0.03

    # Set starting weights
    cumulative_probabilities = update_operator_weights(initial_temperature)

    # Tracking variables
    iteration_count = 0
    start_time = time.time()
    last_print_time = start_time
    last_save_time = start_time
    last_saved_profit = -float('inf')
    last_improvement_time = start_time

    # Track how often each operator is accepted to see effectiveness of operator
    OPERATOR_NAMES = ["relocate", "2-opt", "add", "remove", "swap"]
    operator_attempts  = [0] * 5
    operator_accepted  = [0] * 5
    total_accepted = 0
    total_rejected = 0

    print(f"{'Time':>7} | {'Iter':>12} | {'Temp':>8} | {'Profit':>10} | {'Best':>10} | {'Cust':>5} | {'it/s':>8} | {'Acc%':>6}")
    print("-" * 90)

    # -- 8. Main Optimization Loop --
    while True:
        if iteration_count % 1000 == 0:
            current_time = time.time()
            elapsed_time = current_time - start_time
            if elapsed_time >= time_limit:
                break

        # Debug Dashboard
        if current_time - last_print_time >= DEBUG_INTERVAL:
            elapsed = current_time - start_time
            its_per_sec = iteration_count / elapsed if elapsed > 0 else 0
            total_ops = total_accepted + total_rejected
            acc_ratio = 100.0 * total_accepted / total_ops if total_ops > 0 else 0.0

            # Per-operator acceptance %
            op_stats = "  |  " + "  ".join(
                f"{OPERATOR_NAMES[i]}:{100*operator_accepted[i]/operator_attempts[i]:.0f}%"
                if operator_attempts[i] > 0 else f"{OPERATOR_NAMES[i]}:--"
                for i in range(5)
            )

            print(
                f"{elapsed:6.1f}s | {iteration_count:12,} | {current_temperature:8.4f} | "
                f"€{current_solution.profit:9.2f} | €{best_solution.profit:9.2f} | "
                f"{current_solution.n_customers():5} | {its_per_sec:8.0f} | {acc_ratio:5.1f}%"
                + op_stats
            )
            operator_attempts  = [0] * 5
            operator_accepted  = [0] * 5
            total_accepted = 0
            total_rejected = 0
            last_print_time = current_time

        # Select Operator (Weighted Random Selection)
        random_roll = random.random()
        op_index = len(operator_functions) - 1
        for idx, probability in enumerate(cumulative_probabilities):
            if random_roll < probability:
                op_index = idx
                break
        selected_function = operator_functions[op_index]

        # Generate & Evaluate Move
        move_result = selected_function(current_solution)
        if move_result is not None:
            delta_profit, apply_move_function = move_result
            operator_attempts[op_index] += 1

            # Always accept improvements
            accepted = False
            if delta_profit >= 0:
                apply_move_function()
                accepted = True

            # Otherwise base acceptence rate on temperature
            elif current_temperature > minimum_temperature:
                acceptance_probability = math.exp(delta_profit / current_temperature)
                if random.random() < acceptance_probability:
                    apply_move_function()
                    accepted = True

            # Update trackers
            if accepted:
                operator_accepted[op_index] += 1
                total_accepted += 1
            else:
                total_rejected += 1

            # Update Global Best
            if current_solution.profit > best_solution.profit:
                if current_solution.profit > best_solution.profit + 1:
                    last_improvement_time = current_time
                best_solution = current_solution.clone()
                
        # Reheating Logic
        if current_temperature == minimum_temperature and current_time - last_improvement_time >= REHEAT_INTERVAL:
            REHEAT_RATE = random.random() ** 2 # Randomize reheating rate between 0.5 and 1.0
            current_temperature = initial_temperature *  REHEAT_RATE
            
            last_improvement_time = current_time 
            print(f"Reheating with a Rate of {round(REHEAT_RATE,2)} to a Temperature of T={round(current_temperature,1)}")


        # -- Maintenance --
        # Geometric Cooling: reduce temperature slightly every iteration
        current_temperature = max(current_temperature * cooling_rate, minimum_temperature)
        iteration_count += 1

        # Periodic recompute to prevent floating point drift from incremental updates
        if iteration_count % 100000 == 0:
            current_solution.recompute_profit()
            #currently not used due to static weights
            #cumulative_probabilities = update_operator_weights(current_temperature)
        
        # Write the best solution periodically in the correct format
        if current_time - last_save_time >= SAVE_INTERVAL:
            if best_solution.profit > last_saved_profit:
                # Write the best solution found so far to a file
                best_solution.write("sol.txt", order_ids)
                
            # Update trackers
            last_saved_profit = best_solution.profit
            last_save_time = current_time

    # -- 9. Final Report --
    total_seconds = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"Done: {iteration_count:,} iterations in {total_seconds:.1f}s")
    print(f"Final Best Profit: €{best_solution.profit:.2f}")
    print(f"Customers Served:  {best_solution.n_customers()}")
    print(f"{'=' * 60}")
    
    return best_solution

# -- 10. Entry Point --

def main():
    # File paths
    driving_times_path = "drivingtimes.txt"
    orders_data_path = "orders.txt"
    runtime_limit_seconds = 300 # 5 minutes
    
    # Load Data
    drive_matrix = load_drive(driving_times_path)
    order_ids, nodes, durations, profits, skills = load_orders(orders_data_path)
    
    # Run Optimization Solver
    final_solution = run_simulated_annealing(
        order_ids, 
        nodes, 
        durations, 
        profits, 
        skills, 
        drive_matrix, 
        time_limit=runtime_limit_seconds
    )

if __name__ == "__main__":
    main()