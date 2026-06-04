import numpy as np
from scipy.optimize import minimize
import sys

# -------------------------------------------------------
# PowerFactory Python Path
# -------------------------------------------------------

POWERFACTORY_PYTHON = r"C:\Program Files\DIgSILENT\PowerFactory 2025 SP1\Python\3.13"
sys.path.append(POWERFACTORY_PYTHON)

import powerfactory as pf  # type: ignore

# -------------------------------------------------------
# Connect to PowerFactory
# -------------------------------------------------------

app = pf.GetApplication()

if app is None:
    raise Exception("Cannot connect to PowerFactory")

app.ClearOutputWindow()

# -------------------------------------------------------
# Activate Project and Study Case
# -------------------------------------------------------

project_name = "Transmission System"
study_case_name = "01 Load Flow"


def activate_project_and_case(app, project_name, operating_case):

    if app.ActivateProject(project_name) != 0:
        raise RuntimeError(f"Project not found: {project_name}")

    print(f"Project activated: {project_name}")

    study_cases = app.GetProjectFolder("study").GetContents()

    selected_case = None

    for sc in study_cases:
        if sc.loc_name == operating_case:
            selected_case = sc
            break

    if selected_case:
        selected_case.Activate()
        print(f"Operating case activated: {operating_case}")
    else:
        raise RuntimeError(f"Operating case not found: {operating_case}")


activate_project_and_case(app, project_name, study_case_name)

# -------------------------------------------------------
# Load Flow Command
# -------------------------------------------------------

ldf = app.GetFromStudyCase("ComLdf")

# -------------------------------------------------------
# Generators
# -------------------------------------------------------

generators = app.GetCalcRelevantObjects("*.ElmSym")

if len(generators) == 0:
    raise RuntimeError("No generators found")

controllable_gens = generators

print("\nGenerators found:")

for gen in controllable_gens:
    print(
        f"{gen.loc_name:<15} "
        f"Pgini={gen.pgini:.2f} MW"
    )

# -------------------------------------------------------
# Initial Dispatch
# -------------------------------------------------------

P0 = np.array([g.pgini for g in controllable_gens])

# Use actual PF limits if available
Pmin = np.array([
    float(g.GetAttribute("Pmin_uc"))
    for g in controllable_gens
])

Pmax = np.array([
    float(g.GetAttribute("Pmax_uc"))
    for g in controllable_gens
])

# -------------------------------------------------------
# Lines
# -------------------------------------------------------

lines = app.GetCalcRelevantObjects("*.ElmLne")

# -------------------------------------------------------
# Safe Load Flow Wrapper
# -------------------------------------------------------

def run_loadflow(P):
    """
    Runs load flow after setting generator dispatch.
    Returns True if converged.
    """

    for i, gen in enumerate(controllable_gens):
        gen.pgini = float(P[i])

    err = ldf.Execute()

    # stricter check (PowerFactory sometimes returns non-zero warnings)
    return err == 0


# -------------------------------------------------------
# Constraint: Maximum line loading only (robust version)
# -------------------------------------------------------

def max_loading_constraint(P):

    success = run_loadflow(P)

    if not success:
        # heavy penalty if load flow fails
        return -1e6

    max_loading = 0.0

    for line in lines:
        try:
            loading = float(line.GetAttribute("c:loading"))
            if loading > max_loading:
                max_loading = loading
        except:
            continue

    # SLSQP constraint form: >= 0 must hold
    return 90.0 - max_loading


# -------------------------------------------------------
# Congestion-aware objective (main fix)
# -------------------------------------------------------

def objective(P):

    success = run_loadflow(P)

    if not success:
        return 1e6  # penalize infeasible points

    overload_penalty = 0.0

    for line in lines:
        try:
            loading = float(line.GetAttribute("c:loading"))
            overload_penalty += max(0.0, loading - 90.0)
        except:
            continue

    redispatch_penalty = np.sum(np.abs(P - P0))

    # strong priority to congestion removal
    return 1000.0 * overload_penalty + 0.1 * redispatch_penalty


# -------------------------------------------------------
# Single constraint (IMPORTANT CHANGE)
# -------------------------------------------------------

constraints = [
    {
        "type": "ineq",
        "fun": max_loading_constraint
    }
]


# -------------------------------------------------------
# Bounds (unchanged)
# -------------------------------------------------------

bounds = list(zip(Pmin, Pmax))


# -------------------------------------------------------
# Base Case Check
# -------------------------------------------------------

print("\n========== BASE CASE ==========\n")

run_loadflow(P0)

base_max = 0.0

for line in lines:
    try:
        loading = float(line.GetAttribute("c:loading"))
        base_max = max(base_max, loading)

        if loading > 90:
            print(f"OVERLOADED: {line.loc_name:<25} {loading:.2f}%")
    except:
        pass

print(f"\nBase max loading: {base_max:.2f}%")


# -------------------------------------------------------
# Optimization
# -------------------------------------------------------

print("\nStarting optimization...\n")

result = minimize(
    objective,
    P0,
    method="SLSQP",
    bounds=bounds,
    constraints=constraints,
    options={
        "disp": True,
        "maxiter": 80,
        "ftol": 1e-3
    }
)


# -------------------------------------------------------
# Results
# -------------------------------------------------------

print("\n========== OPTIMIZATION RESULTS ==========\n")

print("Success:", result.success)
print("Message:", result.message)

run_loadflow(result.x)

total_redispatch = 0.0

for i, gen in enumerate(controllable_gens):
    delta = result.x[i] - P0[i]
    total_redispatch += abs(delta)

    print(
        f"{gen.loc_name:<15}"
        f" Initial={P0[i]:8.2f} MW"
        f" New={result.x[i]:8.2f} MW"
        f" Delta={delta:8.2f} MW"
    )

print("\nTotal Redispatch:")
print(f"{total_redispatch:.2f} MW")


# -------------------------------------------------------
# Final Line Loadings
# -------------------------------------------------------

print("\n========== FINAL LINE LOADING ==========\n")

max_loading = 0.0

for line in lines:
    try:
        loading = float(line.GetAttribute("c:loading"))
        max_loading = max(max_loading, loading)

        print(f"{line.loc_name:<30} {loading:8.2f}%")
    except:
        pass

print("\nMaximum Loading After Optimization:")
print(f"{max_loading:.2f}%")