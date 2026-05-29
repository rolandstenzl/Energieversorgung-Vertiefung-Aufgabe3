
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
TIMESTAMP = "24.07.2024 14:00" # Test Max

V_MIN = 0.95
V_MAX = 1.05
LINE_LIMIT = 100.0
STRICT_LIMIT = True

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
                "voltage_kv": bus.GetAttribute("m:u")
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

    bus_csv = []

    for b in buses:

        bus_csv.append({
            "Bus":
                b["name"],
            "Voltage_pu":
                b["voltage_pu"],
            "Voltage_kV":
                b["voltage_kv"],
            "Violation":
                (
                    "Yes"
                    if b["voltage_pu"] is not None
                    and (
                        b["voltage_pu"] < V_MIN
                        or
                        b["voltage_pu"] > V_MAX
                    )
                    else "No"
                )
        })

    export_csv(
        "base_case_buses.csv",
        bus_csv,
        [
            "Bus",
            "Voltage_pu",
            "Voltage_kV",
            "Violation"
        ]
    )

    #==================LINES==================
    lines = get_line_results(app)

    line_csv = []

    for l in lines:

        line_csv.append({
            "Line":
                l["name"],
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

    export_csv(
        "base_case_lines.csv",
        line_csv,
        [
            "Line",
            "Loading_%",
            "Overloaded"
        ]
    )

    #==================TRAFOS==================
    trafos = get_trafo_results(app)

    trafo_csv = []

    for t in trafos:

        trafo_csv.append({
            "Transformer":
                t["name"],
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

    export_csv(
        "base_case_trafos.csv",
        trafo_csv,
        [
            "Transformer",
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
    lines = app.GetCalcRelevantObjects("*.ElmLne")

    results = []

    for line in lines:

        for obj in simout.GetContents("*.ComOutage"):
            obj.Delete()

        out = simout.CreateObject("ComOutage", f"N1_{line.loc_name}")
        out.p_target = line

        if simout.Execute() != 0:
            continue

        results.append({
            "outage": line.loc_name,
            "result": evaluate_network(app)
        })

    # -------------------------------------------------
    # N-1 CSV
    # -------------------------------------------------

    n1_csv = []

    for r in results:

        ov, tv, vv = r["result"]

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
            "Outage":
                r["outage"],
            "Secure":
                (
                    "Yes"
                    if not ov and not tv and not vv
                    else "No"
                ),
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
            "Outage",
            "Secure",
            "LineOverloads",
            "TrafoOverloads",
            "VoltageViolations",
            "MaxLineLoading_%"
        ]
    )

    return results




def run_n2_analysis(app):
    print("\n================ N-2 ANALYSIS ================\n")

    simout = app.GetFromStudyCase("ComSimoutage")
    lines = app.GetCalcRelevantObjects("*.ElmLne")

    results = []

    for l1, l2 in itertools.combinations(lines, 2):

        for obj in simout.GetContents("*.ComOutage"):
            obj.Delete()

        o1 = simout.CreateObject("ComOutage", f"N2A_{l1.loc_name}")
        o2 = simout.CreateObject("ComOutage", f"N2B_{l2.loc_name}")

        o1.p_target = l1
        o2.p_target = l2

        if simout.Execute() != 0:
            continue

        results.append({
            "pair": (l1.loc_name, l2.loc_name),
            "result": evaluate_network(app)
        })

    # -------------------------------------------------
    # N-2 CSV
    # -------------------------------------------------

    n2_csv = []

    for r in results:

        ov, tv, vv = r["result"]

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

        pair = r["pair"]

        n2_csv.append({
            "Outage1":
                pair[0],
            "Outage2":
                pair[1],
            "Secure":
                (
                    "Yes"
                    if not ov and not tv and not vv
                    else "No"
                ),
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
            "Outage1",
            "Outage2",
            "Secure",
            "LineOverloads",
            "TrafoOverloads",
            "VoltageViolations",
            "MaxLineLoading_%"
        ]
    )

    return results


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

    generators = get_controllable_generators(app)

    if not generators:
        print("No controllable generators found.")
        return

    x0 = [g["p0"] for g in generators]
    bounds = [(g["pmin"], g["pmax"]) for g in generators]

    def objective(x):
        return sum(abs(x[i] - generators[i]["p0"]) for i in range(len(x)))

    def constraint_lines(x):

        for i, g in enumerate(generators):
            g["obj"].SetAttribute("pgini", x[i])

        run_load_flow(app)

        line_results = get_line_results(app)

        max_loading = max(
            l["loading"]
            for l in line_results
            if l["loading"] is not None
        )

        return OPT_LINE_LIMIT - max_loading

    cons = [{
        "type": "ineq",
        "fun": constraint_lines
    }]

    res = minimize(
        objective,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=cons
    )

    if not res.success:
        print("Optimization failed:", res.message)
        return

    print("Optimization successful.")

    for i, g in enumerate(generators):
        g["obj"].SetAttribute("pgini", res.x[i])

    # -------------------------------------------------
    # REDISPATCH CSV
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
                res.x[i] - g["p0"]
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

    run_load_flow(app)

    print("\nRedispatch result:")
    for i, g in enumerate(generators):
        print(
            f'{g["name"]}: '
            f'{g["p0"]:.2f} -> {res.x[i]:.2f} MW'
        )


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
    run_n2_analysis(app)

    optimize_redispatch(app)


if __name__ == "__main__":
    main()
