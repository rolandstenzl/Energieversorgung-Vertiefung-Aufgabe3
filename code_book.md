# Code Book

## The script executes the following sequence:

main()
│
├─ connect_powerfactory()
├─ activate_project_and_case()
├─ set_timestamp()
├─ run_load_flow()
│
├─ report_base_case()
│
├─ run_n1_analysis()
│
├─ optimize_redispatch()
│
└─ export results

## Global Variables

POWERFACTORY_PYTHON
PROJECT_NAME
OPERATING_CASE
TIMESTAMP

V_MIN = 0.95
V_MAX = 1.05

OPT_LINE_LIMIT - entweder STRICT_LIMIT oder nicht 90/80

## Connection to PF

### connect_powerfactory()
connection to the API

### activate_project_and_case()
Selects project by name (study case ist leer weil er dann einfach den aktuellen nimmt - wäre "1 Load Flow") 

### set_timestamp
Sets time to the correct time. (kann man auch in PF direkt einstellen und die Fkt weglassen.)

### run_load_flow
This is just just the load flow execute from PF

### get_bus_results
This is supposed to read out data from the load flow. (m:... sind immer die Variablen in PF. ich hab die einfach in PF über das display window nachgeschaut. Die stimmen aber nicht immer überein..)

### get_line_results
holt sich alle line loadings mit c:loading. is in %
### get_trafo_results
same same but trafo

### short_path
creates a shorter and more readable path for the csv output. instead of the full path you only get area and bus number.

### export_csv
creates csv - fielpath, csv, header, input. (für line trafo n-1 etc.)

### report_base_case
checks for violations and exports csv

### evaluate_network
gibt violations als listen zurück: (
    overloaded_lines,
    overloaded_trafos,
    voltage_violations
)

### run_n1_analysis
makes contingency list and goes through list turning of each element. then load flow -> csv

### run_n2_analysis
würd ich ignorieren. war ja nicht gefragt.
macht aber im prinzip das gleiche wie n-1 nur das er immer 2 objekte still legt. dauert dadruch halt ewig und ich bin mir nicht sicher obs funktioniert.

## Task 5 (the juicy bits)

### get_controllable_generators
da sollten wir alle generatoren in eine liste bekommen und drei Werte auslesen:
- m:Psum:bus1 sollte die aktuelle leistung des generators in der letzten loadflow berechnung sein.. da hab ich aber schon einige sache  durchprobiert und bim mir nicht sicher ob das jetzt der richtige wert ist.
- Pmin_uc / Pmax_uc sind die obere und untere grenze in PF die aber bei der load flow analyse irgendwie manchmal ignoriert werden. zB beim Slack. der liefert immer einfach den rest.
return: [
    {
        "obj": generator,
        "name": "...",
        "p_actual": ...,
        "pmin": ...,
        "pmax": ...
    }
]

### optimize_redispatch
da wirds jetzt wild. erst holen wir uns die generatoren.
dann hab ich über x0 versucht aktuelle einstellungen zu übernehmen. das ist der Startpunkt für den optimizer.

#### apply_dispatch
da sollte ein neuer wert übergeben werden an PF um die generatoren umzustellen aber ob pgini richtig ist is fraglich. es gibt auch noch plini. die Doku schweigt dazu...

#### objective
hier wird jetzt startwert an pf übergeben mit apply_dispatch dann load_flow. Hier habe ich jetzt mit penalty gearbeitet und das ganze quadratisch gemacht.. (im nachhinein weiss ich nicht ob das clever war aber sonst bin ich immer instant in den bounds gelandet oder hatte einen unmöglichen startwert)

#### constraint_basecase
checkt einfach nur ob der base case schon innerhalb der grenzen liegt. wenn die margains kleiner null sind leigen wir draußen.

#### constraint_balance
das redispatch sich auf 0 ausgeht.

#### constraint_n1
kann man auch ignorieren da die optimierung ohne n-1 eh auch schon fraglich hinhaut. hätte aber für jeden n-1 case einen redispatch finden sollen.

#### Optimization
    res = minimize(

        objective,

        x0,

        method="SLSQP",

        bounds=bounds,

        constraints=constraints,

        options={

            "maxiter": 100,
            "ftol": 1e-5,
            "eps": 1.0,
            "disp": True
        }
    )
Hier ist dann der eigentliche optimierungs befehl. mit objective als Zielfunktion und x0 als entscheidungsvariable.

