
import sys
import itertools
from scipy.optimize import minimize
from datetime import datetime
import csv
import os

# =========================================================
# CONFIGURATION 
# =========================================================

POWERFACTORY_PYTHON = r"C:\Program Files\DIgSILENT\PowerFactory 2025 SP1\Python\3.13"
PROJECT_NAME = "Transmission System"
OPERATING_CASE = " "
TIMESTAMP = "24.07.2024 14:00" # Test Max Test Josef

V_MIN = 0.95
V_MAX = 1.05
LINE_LIMIT = 100.0
STRICT_LIMIT = True
ENABLE_N1_REDISPATCH = False


OPT_LINE_LIMIT = (
    80.0
    if STRICT_LIMIT
    else 90.0
)

# =========================================================
# OUTPUT SETTINGS
# =========================================================

OUTPUT_DIR = "results_csv"

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)

sys.path.append(POWERFACTORY_PYTHON)

import powerfactory as pf  # type: ignore

# =========================================================
# CONNECTION / SETUP
# =========================================================

def connect_powerfactory():
    app = pf.GetApplication()

    if not app:
        raise RuntimeError("PowerFactory not available. Close PF and retry.")

    return app


def set_timestamp(app, timestamp_str):

    study_case = app.GetActiveStudyCase()

    if not study_case:
        raise RuntimeError("No active study case.")

    dt = datetime.strptime(
        timestamp_str,
        "%d.%m.%Y %H:%M"
    )

    # PowerFactory uses Unix timestamp (seconds)
    pf_time = int(dt.timestamp())

    study_case.SetStudyTime(pf_time)

    print(
        f"Study time set to: "
        f"{timestamp_str}"
    )

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
        print(f"Operating case not found: {operating_case}")
        print("Using currently active study case.")


# =========================================================
# LOAD FLOW
# =========================================================

def run_load_flow(app):
    ldf = app.GetFromStudyCase("ComLdf")

    if not ldf:
        raise RuntimeError("ComLdf not found.")

    err = ldf.Execute()

    if err != 0:
        raise RuntimeError("Load flow failed.")

    print("Load flow successful.")


# =========================================================
# DATA EXTRACTION
# =========================================================

def get_bus_results(app):
    buses = app.GetCalcRelevantObjects("*.ElmTerm")
    results = []

    for bus in buses:
        try:
            results.append({
                "name": bus.loc_name,
                "voltage_pu": bus.GetAttribute("m:u1"),
                "voltage_kv": bus.GetAttribute("m:U")
            })
        except:
            continue

    return results


def get_line_results(app):
    lines = app.GetCalcRelevantObjects("*.ElmLne")
    results = []

    for line in lines:
        try:
            results.append({
                "obj": line,
                "name": line.loc_name,
                "loading": line.GetAttribute("c:loading")
            })
        except:
            continue

    return results


def get_trafo_results(app):
    trafos = app.GetCalcRelevantObjects("*.ElmTr2")
    results = []

    for tr in trafos:
        try:
            results.append({
                "name": tr.loc_name,
                "loading": tr.GetAttribute("c:loading")
            })
        except:
            continue

    return results


# =========================================================
# PATH HELPER
# =========================================================

def short_path(obj):

    try:
        full = obj.GetFullName()

        parts = full.split("\\")

        # keep only last two folders + object
        if len(parts) >= 2:
            return "\\".join(parts[-2:])
        else:
            return full

    except:
        return obj.loc_name

# =========================================================
# CSV EXPORT
# =========================================================

def export_csv(filename, data, fieldnames):

    path = os.path.join(
        OUTPUT_DIR,
        filename
    )

    with open(
        path,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(data)

    print(
        f"CSV exported: {path}"
    )

# =========================================================
# REPORTING
# =========================================================

def report_base_case(app):
    print("\n================ BASE CASE ANALYSIS ================\n")

    #==================BUSES==================
    buses = get_bus_results(app)

    # -------------------------------------------------
    # BUS CSV (SAME LOGIC AS TRAFOS / LINES)
    # -------------------------------------------------

    bus_csv = []

    for bus in app.GetCalcRelevantObjects("*.ElmTerm"):

        try:

            vpu = bus.GetAttribute("m:u1")
            vkv = bus.GetAttribute("m:Ul")

            bus_csv.append({

                "Bus":
                    short_path(bus),

                "Nominal_kV":
                    bus.GetAttribute("uknom"),

                "Voltage_pu":
                    vpu,

                "Voltage_kV":
                    vkv,

                "Violation":
                    (
                        "Yes"
                        if vpu is not None
                        and (
                            vpu < V_MIN
                            or
                            vpu > V_MAX
                        )
                        else "No"
                    )
            })

        except:
            continue

    export_csv(
        "base_case_buses.csv",
        bus_csv,
        [
            "Bus",
            "Nominal_kV",
            "Voltage_pu",
            "Voltage_kV",
            "Violation"
        ]
    )


    #==================LINES==================
    lines = get_line_results(app)
    # -------------------------------------------------
    # LINE CSV (PHYSICAL ASSETS)
    # -------------------------------------------------

    line_csv = []

    for l in lines:

        try:

            line_csv.append({

                "Line":
                    short_path(l["obj"]),

                "FromBus":
                    short_path(
                        l["obj"].bus1.cterm
                    ),

                "ToBus":
                    short_path(
                        l["obj"].bus2.cterm
                    ),

                "Loading_%":
                    l["loading"],

                "Overloaded":
                    (
                        "Yes"
                        if l["loading"] is not None
                        and l["loading"] > LINE_LIMIT
                        else "No"
                    )
            })

        except:
            continue

    export_csv(
        "base_case_lines.csv",
        line_csv,
        [
            "Line",
            "FromBus",
            "ToBus",
            "Loading_%",
            "Overloaded"
        ]
    )

    #==================TRAFOS==================
    trafos = get_trafo_results(app)

    # -------------------------------------------------
    # TRAFO CSV (PHYSICAL ASSETS)
    # -------------------------------------------------

    trafo_csv = []

    for t in trafos:

        try:

            tr_obj = next(
                tr for tr in
                app.GetCalcRelevantObjects("*.ElmTr2")
                if tr.loc_name == t["name"]
            )

            trafo_csv.append({

                "Transformer":
                    short_path(tr_obj),

                "HV_Bus":
                    short_path(
                        tr_obj.bushv.cterm
                    ),

                "LV_Bus":
                    short_path(
                        tr_obj.buslv.cterm
                    ),

                "Loading_%":
                    t["loading"],

                "Overloaded":
                    (
                        "Yes"
                        if t["loading"] is not None
                        and t["loading"] > LINE_LIMIT
                        else "No"
                    )
            })

        except:
            continue

    export_csv(
        "base_case_trafos.csv",
        trafo_csv,
        [
            "Transformer",
            "HV_Bus",
            "LV_Bus",
            "Loading_%",
            "Overloaded"
        ]
    )

    voltage_violations = [
        b for b in buses
        if b["voltage_pu"] is not None
        and (b["voltage_pu"] < V_MIN or b["voltage_pu"] > V_MAX)
    ]

    line_overloads = [
        l for l in lines
        if l["loading"] is not None
        and l["loading"] > LINE_LIMIT
    ]

    trafo_overloads = [
        t for t in trafos
        if t["loading"] is not None
        and t["loading"] > LINE_LIMIT
    ]

    print("Voltage violations:")
    if voltage_violations:
        for b in voltage_violations:
            print(f'  {b["name"]}: {b["voltage_pu"]:.3f} pu')
    else:
        print("  None")

    print("\nLine overloads:")
    if line_overloads:
        for l in line_overloads:
            print(f'  {l["name"]}: {l["loading"]:.1f}%')
    else:
        print("  None")

    print("\nTransformer overloads:")
    if trafo_overloads:
        for t in trafo_overloads:
            print(f'  {t["name"]}: {t["loading"]:.1f}%')
    else:
        print("  None")

    print("\nTop 10 heavily loaded lines:")
    sorted_lines = sorted(
        [l for l in lines if l["loading"] is not None],
        key=lambda x: x["loading"],
        reverse=True
    )

    for l in sorted_lines[:10]:
        print(f'  {l["name"]}: {l["loading"]:.1f}%')


# =========================================================
# CONTINGENCY ANALYSIS
# =========================================================

def evaluate_network(app):
    buses = app.GetCalcRelevantObjects("*.ElmTerm")
    lines = app.GetCalcRelevantObjects("*.ElmLne")
    trafos = app.GetCalcRelevantObjects("*.ElmTr2")

    overloaded_lines = []
    overloaded_trafos = []
    voltage_violations = []

    for l in lines:
        try:
            loading = l.GetAttribute("c:loading")
            if loading is not None and loading > LINE_LIMIT:
                overloaded_lines.append((l.loc_name, loading))
        except:
            pass

    for t in trafos:
        try:
            loading = t.GetAttribute("c:loading")
            if loading is not None and loading > LINE_LIMIT:
                overloaded_trafos.append((t.loc_name, loading))
        except:
            pass

    for b in buses:
        try:
            v = b.GetAttribute("m:u1")
            if v is not None and (v < V_MIN or v > V_MAX):
                voltage_violations.append((b.loc_name, v))
        except:
            pass

    return overloaded_lines, overloaded_trafos, voltage_violations


def run_n1_analysis(app):

    print("\n================ N-1 ANALYSIS ================\n")

    simout = app.GetFromStudyCase("ComSimoutage")

    # -------------------------------------------------
    # CONTINGENCY SET
    # -------------------------------------------------

    contingencies = []

    # Line outages
    for l in app.GetCalcRelevantObjects("*.ElmLne"):
        contingencies.append(("Line", l))

    # Transformer outages
    for t in app.GetCalcRelevantObjects("*.ElmTr2"):
        contingencies.append(("Transformer", t))

    # Generator outages
    for g in app.GetCalcRelevantObjects("*.ElmSym"):
        contingencies.append(("Generator", g))

    results = []

    # -------------------------------------------------
    # RUN CONTINGENCIES
    # -------------------------------------------------

    for ctype, element in contingencies:

        # Delete old outages
        for obj in simout.GetContents("*.ComOutage"):
            obj.Delete()

        # Create outage
        out = simout.CreateObject(
            "ComOutage",
            f"N1_{ctype}_{element.loc_name}"
        )

        out.p_target = element

        # Execute contingency
        err = simout.Execute()

        run_load_flow(app)

        if err != 0:

            results.append({
                "type": ctype,
                "outage": element.loc_name,
                "converged": False,
                "result": None
            })

            continue

        # Evaluate network after outage
        result = evaluate_network(app)

        results.append({
            "type": ctype,
            "outage": element.loc_name,
            "converged": True,
            "result": result
        })

    # -------------------------------------------------
    # N-1 CSV
    # -------------------------------------------------

    n1_csv = []

    for r in results:

        # Non-convergent contingency
        if not r["converged"]:

            n1_csv.append({

                "ContingencyType":
                    r["type"],

                "Outage":
                    r["outage"],

                "Secure":
                    "No",

                "Converged":
                    "No",

                "LineOverloads":
                    "N/A",

                "TrafoOverloads":
                    "N/A",

                "VoltageViolations":
                    "N/A",

                "MaxLineLoading_%":
                    "N/A"
            })

            continue

        ov, tv, vv = r["result"]

        # Determine max line loading
        max_loading = 0

        for l in app.GetCalcRelevantObjects("*.ElmLne"):

            try:

                load = l.GetAttribute("c:loading")

                if load is not None:

                    max_loading = max(
                        max_loading,
                        load
                    )

            except:
                pass

        n1_csv.append({

            "ContingencyType":
                r["type"],

            "Outage":
                r["outage"],

            "Secure":
                (
                    "Yes"
                    if not ov and not tv and not vv
                    else "No"
                ),

            "Converged":
                "Yes",

            "LineOverloads":
                len(ov),

            "TrafoOverloads":
                len(tv),

            "VoltageViolations":
                len(vv),

            "MaxLineLoading_%":
                max_loading
        })

    export_csv(

        "n1_summary.csv",

        n1_csv,

        [
            "ContingencyType",
            "Outage",
            "Secure",
            "Converged",
            "LineOverloads",
            "TrafoOverloads",
            "VoltageViolations",
            "MaxLineLoading_%"
        ]
    )

    return results



'''
def run_n2_analysis(app):

    print("\n================ N-2 ANALYSIS ================\n")

    simout = app.GetFromStudyCase("ComSimoutage")

    # -------------------------------------------------
    # CONTINGENCY SET
    # -------------------------------------------------

    contingencies = []

    # Lines
    for l in app.GetCalcRelevantObjects("*.ElmLne"):
        contingencies.append(("Line", l))

    # Transformers
    for t in app.GetCalcRelevantObjects("*.ElmTr2"):
        contingencies.append(("Transformer", t))

    # Generators
    for g in app.GetCalcRelevantObjects("*.ElmSym"):
        contingencies.append(("Generator", g))

    results = []

    # -------------------------------------------------
    # RUN N-2 CONTINGENCIES
    # -------------------------------------------------

    for (type1, elem1), (type2, elem2) in itertools.combinations(contingencies, 2):

        # Delete old outages
        for obj in simout.GetContents("*.ComOutage"):
            obj.Delete()

        # Create first outage
        o1 = simout.CreateObject(
            "ComOutage",
            f"N2A_{type1}_{elem1.loc_name}"
        )

        o1.p_target = elem1

        # Create second outage
        o2 = simout.CreateObject(
            "ComOutage",
            f"N2B_{type2}_{elem2.loc_name}"
        )

        o2.p_target = elem2

        # Execute contingency
        err = simout.Execute()

        run_load_flow(app)
    

        # Non-convergent case
        if err != 0:

            results.append({

                "type1":
                    type1,

                "outage1":
                    elem1.loc_name,

                "type2":
                    type2,

                "outage2":
                    elem2.loc_name,

                "converged":
                    False,

                "result":
                    None
            })

            continue

        # Evaluate post-contingency network
        result = evaluate_network(app)

        results.append({

            "type1":
                type1,

            "outage1":
                elem1.loc_name,

            "type2":
                type2,

            "outage2":
                elem2.loc_name,

            "converged":
                True,

            "result":
                result
        })

    # -------------------------------------------------
    # N-2 CSV
    # -------------------------------------------------

    n2_csv = []

    for r in results:

        # Non-convergent case
        if not r["converged"]:

            n2_csv.append({

                "ContingencyType1":
                    r["type1"],

                "Outage1":
                    r["outage1"],

                "ContingencyType2":
                    r["type2"],

                "Outage2":
                    r["outage2"],

                "Secure":
                    "No",

                "Converged":
                    "No",

                "LineOverloads":
                    "N/A",

                "TrafoOverloads":
                    "N/A",

                "VoltageViolations":
                    "N/A",

                "MaxLineLoading_%":
                    "N/A"
            })

            continue

        ov, tv, vv = r["result"]

        # Determine maximum line loading
        max_loading = 0

        for l in app.GetCalcRelevantObjects("*.ElmLne"):

            try:

                load = l.GetAttribute("c:loading")

                if load is not None:

                    max_loading = max(
                        max_loading,
                        load
                    )

            except:
                pass

        n2_csv.append({

            "ContingencyType1":
                r["type1"],

            "Outage1":
                r["outage1"],

            "ContingencyType2":
                r["type2"],

            "Outage2":
                r["outage2"],

            "Secure":
                (
                    "Yes"
                    if not ov and not tv and not vv
                    else "No"
                ),

            "Converged":
                "Yes",

            "LineOverloads":
                len(ov),

            "TrafoOverloads":
                len(tv),

            "VoltageViolations":
                len(vv),

            "MaxLineLoading_%":
                max_loading
        })

    export_csv(

        "n2_summary.csv",

        n2_csv,

        [
            "ContingencyType1",
            "Outage1",
            "ContingencyType2",
            "Outage2",
            "Secure",
            "Converged",
            "LineOverloads",
            "TrafoOverloads",
            "VoltageViolations",
            "MaxLineLoading_%"
        ]
    )

    return results
'''

# =========================================================
# TASK 5 – ACTIVE POWER REDISPATCH / CURTAILMENT
# =========================================================

def get_controllable_generators(app):
    gens = app.GetCalcRelevantObjects("*.ElmSym")

    controllable = []

    for g in gens:
        try:
            p = g.GetAttribute("pgini")
            pmin = g.GetAttribute("Pmin_uc")
            pmax = g.GetAttribute("Pmax_uc")

            if p is None:
                continue

            controllable.append({
                "obj": g,
                "name": g.loc_name,
                "p0": p,
                "pmin": pmin if pmin is not None else 0.0,
                "pmax": pmax if pmax is not None else p
            })

        except:
            continue

    return controllable



def optimize_redispatch(app):

    print("\n================ REDISPATCH OPTIMIZATION ================\n")


    # -------------------------------------------------
    # GENERATORS
    # -------------------------------------------------

    generators = get_controllable_generators(app)


    if not generators:
        print("No controllable generators found.")
        return

    x0 = []

    for g in generators:

        p0 = g["p0"]
        pmin = g["pmin"]
        pmax = g["pmax"]

        if p0 < pmin:
            p0 = pmin
        elif p0 > pmax:
            p0 = pmax

        x0.append(p0)

    bounds = [
        (g["pmin"], g["pmax"])
        for g in generators
    ]

    total_generation = sum(x0)

    # -------------------------------------------------
    # HELPER
    # -------------------------------------------------

    def apply_dispatch(x):

        for i, g in enumerate(generators):

            g["obj"].SetAttribute(
                "pgini",
                float(x[i])
            )

    # -------------------------------------------------
    # OBJECTIVE
    # -------------------------------------------------

    def objective(x):

        return sum(
            (
                x[i]
                - generators[i]["p0"]
            ) ** 2
            for i in range(len(x))
        )

    # -------------------------------------------------
    # POWER BALANCE
    # -------------------------------------------------

    def constraint_balance(x):

        return (
            sum(x)
            - total_generation
        )

    # -------------------------------------------------
    # BASE CASE LINE LIMITS
    # -------------------------------------------------

    def constraint_basecase(x):

        apply_dispatch(x)

        try:
            run_load_flow(app)
        except:
            return -1000

        margins = []

        for line in app.GetCalcRelevantObjects("*.ElmLne"):

            try:

                loading = line.GetAttribute(
                    "c:loading"
                )

                if loading is not None:

                    margins.append(
                        OPT_LINE_LIMIT
                        - loading
                    )

            except:
                pass

        if not margins:
            return -1000

        return min(margins)

    # -------------------------------------------------
    # OPTIONAL N-1 SECURITY
    # -------------------------------------------------

    def constraint_n1(x):

        apply_dispatch(x)

        simout = app.GetFromStudyCase(
            "ComSimoutage"
        )

        lines = app.GetCalcRelevantObjects(
            "*.ElmLne"
        )

        worst_margin = 1e9

        for outage_line in lines:

            # clear previous outages
            for obj in simout.GetContents(
                "*.ComOutage"
            ):
                obj.Delete()

            out = simout.CreateObject(
                "ComOutage",
                f"N1_{outage_line.loc_name}"
            )

            out.p_target = outage_line

            err = simout.Execute()

            if err != 0:
                return -1000

            try:
                run_load_flow(app)
            except:
                return -1000

            for line in lines:

                try:

                    loading = line.GetAttribute(
                        "c:loading"
                    )

                    if loading is not None:

                        margin = (
                            OPT_LINE_LIMIT
                            - loading
                        )

                        worst_margin = min(
                            worst_margin,
                            margin
                        )

                except:
                    pass

        # clean up outages
        for obj in simout.GetContents(
            "*.ComOutage"
        ):
            obj.Delete()

        run_load_flow(app)

        return worst_margin

    # -------------------------------------------------
    # CONSTRAINTS
    # -------------------------------------------------

    constraints = [

        {
            "type": "ineq",
            "fun": constraint_basecase
        },

        {
            "type": "eq",
            "fun": constraint_balance
        }

    ]

    if ENABLE_N1_REDISPATCH:

        constraints.append(
            {
                "type": "ineq",
                "fun": constraint_n1
            }
        )

#==========================DEBUG==================== Problems with base-case values    
    print("\nGenerator bounds:")

    for g in generators:

        print(
            g["name"],
            "P0 =", g["p0"],
            "Pmin =", g["pmin"],
            "Pmax =", g["pmax"]
        )

    print(
        "\nBase-case constraint value:",
        constraint_basecase(x0)
    )

    print(
        "Balance constraint value:",
        constraint_balance(x0)
    )




    # -------------------------------------------------
    # OPTIMIZATION
    # -------------------------------------------------

    res = minimize(
        objective,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints
    )

    # -------------------------------------------------
    # CHECK RESULT
    # -------------------------------------------------

    if not res.success:

        print(
            "Optimization failed:",
            res.message
        )

        return

    print(
        "Optimization successful."
    )

    apply_dispatch(res.x)

    run_load_flow(app)

    # -------------------------------------------------
    # CSV EXPORT
    # -------------------------------------------------

    redispatch_csv = []

    for i, g in enumerate(generators):

        redispatch_csv.append({

            "Generator":
                g["name"],

            "P_before_MW":
                g["p0"],

            "P_after_MW":
                res.x[i],

            "Redispatch_MW":
                res.x[i]
                - g["p0"]

        })

    export_csv(

        "redispatch_results.csv",

        redispatch_csv,

        [
            "Generator",
            "P_before_MW",
            "P_after_MW",
            "Redispatch_MW"
        ]

    )

    print("\nRedispatch result:")

    for i, g in enumerate(generators):

        print(

            f'{g["name"]}: '
            f'{g["p0"]:.2f} -> '
            f'{res.x[i]:.2f} MW'

        )

    # -------------------------------------------------
    # FINAL NETWORK STATE
    # -------------------------------------------------

    print("\nFinal line loadings:")

    for line in app.GetCalcRelevantObjects(
        "*.ElmLne"
    ):

        try:

            loading = line.GetAttribute(
                "c:loading"
            )

            if loading is not None:

                print(
                    f"{line.loc_name}: "
                    f"{loading:.1f}%"
                )

        except:
            pass



# =========================================================
# MAIN
# =========================================================

def main():
    app = connect_powerfactory()

    activate_project_and_case(
        app,
        PROJECT_NAME,
        OPERATING_CASE,
    )


    set_timestamp(
        app,
        TIMESTAMP
    )


    run_load_flow(app)

    report_base_case(app)

    run_n1_analysis(app)
    #run_n2_analysis(app)

    optimize_redispatch(app)


if __name__ == "__main__":
    main()
