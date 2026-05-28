import sys
import os
import csv

sys.path.append(
    r"C:\Program Files\DIgSILENT\PowerFactory 2025 SP1\Python\3.13"
)

import powerfactory as pf # type: ignore

app = pf.GetApplication()

if not app:
    print("Close PowerFactory and retry.")
    sys.exit()

project_name = "Transmission System"

if app.ActivateProject(project_name) != 0:
    print("Project not found.")
    sys.exit()

print("Project active.")

ldf = app.GetFromStudyCase("ComLdf")

if ldf.Execute() != 0:
    print("Load flow failed.")
    sys.exit()

print("Load flow successful.")

# ------------------
# BUS VOLTAGES
# ------------------

busbars = app.GetCalcRelevantObjects("*.ElmTerm")

voltage_results = []

for bus in busbars:

    try:
        voltage_results.append({
            "Bus": bus.loc_name,
            "Voltage_kV": bus.GetAttribute("m:u"),
            "Voltage_pu": bus.GetAttribute("m:u1")
        })
    except:
        pass

# Voltage violations

violations = [
    v for v in voltage_results
    if v["Voltage_pu"] < 0.95
    or v["Voltage_pu"] > 1.05
]

print("\nVoltage Violations")

for v in violations:
    print(v)

# ------------------
# LINES
# ------------------

lines = app.GetCalcRelevantObjects("*.ElmLne")

for line in lines:

    loading = line.GetAttribute("c:loading")

    if loading > 100:
        print(
            f"Line overload: "
            f"{line.loc_name} {loading:.1f}%"
        )

# ------------------
# TRANSFORMERS
# ------------------

trafos = app.GetCalcRelevantObjects("*.ElmTr2")

for tr in trafos:

    loading = tr.GetAttribute("c:loading")

    if loading > 100:
        print(
            f"Trafo overload: "
            f"{tr.loc_name} {loading:.1f}%"
        )


        
simout = app.GetFromStudyCase("ComSimoutage")

if not simout:
    print("No contingency module.")
    sys.exit()

lines = app.GetCalcRelevantObjects("*.ElmLne")

# remove old auto cases
for c in simout.GetContents("Auto_*"):
    c.Delete()

# create N-1
for line in lines:

    outage = simout.CreateObject(
        "ComOutage",
        f"Auto_{line.loc_name}"
    )

    outage.p_target = line

print("Cases created.")

# execute
err = simout.Execute()

res = app.GetFromStudyCase("*.ElmRes")
print(f"stored here:",res)

all_res = app.GetCalcRelevantObjects("*.ElmRes")

for r in all_res:
    print(r.loc_name)

if err == 0:
    print("N-1 successful.")
else:
    print("Failed.")


# -----------------------------
# COLLECT ELEMENTS
# -----------------------------
lines = app.GetCalcRelevantObjects("*.ElmLne")
buses = app.GetCalcRelevantObjects("*.ElmTerm")
trafos = app.GetCalcRelevantObjects("*.ElmTr2")

# =========================================================
# BASE CASE LOAD FLOW REPORT
# =========================================================

print("\n================ BASE CASE ANALYSIS ================\n")

# -----------------------------
# BUS VOLTAGES
# -----------------------------
print("\n============= VOLTAGE ANALYSIS =============")

voltage_violations = []

for b in busbars:

    try:
        v = b.GetAttribute("m:u1")

        if v is None:
            continue

        if v < 0.95 or v > 1.05:
            voltage_violations.append((b.loc_name, v))

    except:
        continue

if not voltage_violations:
    print("Status: SECURE")
else:
    print("Status: VIOLATION")

    print("Voltage violations:")
    for name, v in voltage_violations:
        print(f"  {name}: {v:.3f} pu")


# -----------------------------
# LINE LOADING
# -----------------------------
print("\n============= LINE LOADING =============")

line_overloads = []

for line in lines:

    try:
        loading = line.GetAttribute("c:loading")

        if loading is None:
            continue

        if loading > 100:
            line_overloads.append((line.loc_name, loading))

    except:
        continue

if not line_overloads:
    print("Status: No Overload")
else:
    print("Status: OVERLOAD")

    print("Line overloads:")
    for name, load in line_overloads:
        print(f"  {name}: {load:.1f}%")


# -----------------------------
# TRANSFORMER LOADING
# -----------------------------
print("\n============= TRANSFORMER LOADING =============")

trafo_overloads = []

for tr in trafos:

    try:
        loading = tr.GetAttribute("c:loading")

        if loading is None:
            continue

        if loading > 100:
            trafo_overloads.append((tr.loc_name, loading))

    except:
        continue

if not trafo_overloads:
    print("Status: No Overloads")
else:
    print("Status: OVERLOAD")

    print("Transformer overloads:")
    for name, load in trafo_overloads:
        print(f"  {name}: {load:.1f}%")

# =========================================================
# CONTINGENCY OBJECT
# =========================================================
simout = app.GetFromStudyCase("ComSimoutage")

# remove old outages
for obj in simout.GetContents("*.ComOutage"):
    obj.Delete()

# =========================================================
# N-1 ANALYSIS
# =========================================================
print("\n================ N-1 ANALYSIS ================\n")

n1_results = []

for outage_line in lines:

    # clean previous contingency
    for obj in simout.GetContents("*.ComOutage"):
        obj.Delete()

    # create outage
    out = simout.CreateObject(
        "ComOutage",
        "N1_" + outage_line.loc_name
    )
    out.p_target = outage_line

    # run contingency
    err = simout.Execute()

    if err != 0:
        print("Load flow failed for outage:",
              outage_line.loc_name)
        continue

    overloaded_lines = []
    overloaded_trafos = []
    voltage_violations = []

    # -----------------------------
    # LINES
    # -----------------------------
    for l in lines:

        try:
            loading = l.GetAttribute("c:loading")

            if loading is not None and loading > 100:
                overloaded_lines.append(
                    (l.loc_name, loading)
                )

        except:
            continue

    # -----------------------------
    # TRAFOS
    # -----------------------------
    for t in trafos:

        try:
            loading = t.GetAttribute("c:loading")

            if loading is not None and loading > 100:
                overloaded_trafos.append(
                    (t.loc_name, loading)
                )

        except:
            continue

    # -----------------------------
    # VOLTAGES
    # -----------------------------
    for b in buses:

        try:
            v = b.GetAttribute("m:u1")

            if v is None:
                continue

            if v < 0.95 or v > 1.05:
                voltage_violations.append(
                    (b.loc_name, v)
                )

        except:
            continue

    n1_results.append({
        "outage": outage_line.loc_name,
        "overloads": overloaded_lines,
        "trafos": overloaded_trafos,
        "voltages": voltage_violations
    })

# -----------------------------
# PRINT N-1 SUMMARY
# -----------------------------
print("\n============= N-1 SUMMARY =============")

for r in n1_results:

    print("\nOutage:", r["outage"])

    ov = r["overloads"]
    tv = r["trafos"]
    vv = r["voltages"]

    if not ov and not tv and not vv:
        #continue
        print("Status: SECURE")

    else:
        print("Status: VIOLATION")

        if ov:
            print("Line overloads:")
            for name, load in ov:
                print(f"  {name}: {load:.1f}%")

        if tv:
            print("Transformer overloads:")
            for name, load in tv:
                print(f"  {name}: {load:.1f}%")

        if vv:
            print("Voltage violations:")
            for name, v in vv:
                print(f"  {name}: {v:.3f} pu")


# =========================================================
# N-2 ANALYSIS
# =========================================================
print("\n================ N-2 ANALYSIS ================\n")

# TEMPORARY:
# all line pairs
# later replace with real common-mode filter
import itertools

pairs = list(
    itertools.combinations(lines, 2)
)

print("N-2 cases:", len(pairs))

n2_results = []

for l1, l2 in pairs:

    # clear previous
    for obj in simout.GetContents("*.ComOutage"):
        obj.Delete()

    o1 = simout.CreateObject(
        "ComOutage",
        "N2A_" + l1.loc_name
    )
    o2 = simout.CreateObject(
        "ComOutage",
        "N2B_" + l2.loc_name
    )

    o1.p_target = l1
    o2.p_target = l2

    err = simout.Execute()

    if err != 0:
        print("N-2 failed:",
              l1.loc_name,
              l2.loc_name)
        continue

    overloaded_lines = []
    overloaded_trafos = []
    voltage_violations = []

    # -----------------------------
    # LINES
    # -----------------------------
    for l in lines:

        try:
            loading = l.GetAttribute("c:loading")

            if loading is not None and loading > 100:
                overloaded_lines.append(
                    (l.loc_name, loading)
                )

        except:
            continue

    # -----------------------------
    # TRAFOS
    # -----------------------------
    for t in trafos:

        try:
            loading = t.GetAttribute("c:loading")

            if loading is not None and loading > 100:
                overloaded_trafos.append(
                    (t.loc_name, loading)
                )

        except:
            continue

    # -----------------------------
    # VOLTAGES
    # -----------------------------
    for b in buses:

        try:
            v = b.GetAttribute("m:u1")

            if v is None:
                continue

            if v < 0.95 or v > 1.05:
                voltage_violations.append(
                    (b.loc_name, v)
                )

        except:
            continue

    n2_results.append({
        "outage_pair":
            (l1.loc_name, l2.loc_name),
        "overloads":
            overloaded_lines,
        "trafos":
            overloaded_trafos,
        "voltages":
            voltage_violations
    })

# -----------------------------
# PRINT N-2 SUMMARY
# -----------------------------
print("\n============= N-2 SUMMARY =============")

for r in n2_results:

    pair = r["outage_pair"]
    ov = r["overloads"]
    tv = r["trafos"]
    vv = r["voltages"]

    print("\nOutage pair:", pair)

    if not ov and not tv and not vv:
        print("Status: SECURE")

    else:
        print("Status: VIOLATION")

        if ov:
            print("Line overloads:")
            for name, load in ov:
                print(f"  {name}: {load:.1f}%")

        if tv:
            print("Transformer overloads:")
            for name, load in tv:
                print(f"  {name}: {load:.1f}%")

        if vv:
            print("Voltage violations:")
            for name, v in vv:
                print(f"  {name}: {v:.3f} pu")