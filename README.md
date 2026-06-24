# FP&A tests

Two finance-as-code demos.

## simple-budget
YAML assumptions + Python budget engine, scenarios, BvA vs actuals.

```
python build_budget.py all
streamlit run dashboards/app.py
streamlit run dashboards/app_bva.py
```

## driver-model
Cascading driver-based plan (capacity -> pipeline -> wins -> revenue), multi-source input resolver, live sensitivity dashboard.

```
python engine.py
streamlit run dashboards/app_driver.py
```
