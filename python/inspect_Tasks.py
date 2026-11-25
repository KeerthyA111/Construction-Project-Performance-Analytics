from decimal import Decimal
from pathlib import Path
import pandas as pn

tasks = pn.read_csv(Path(__file__).parent / "Tasks.csv")
print(tasks.head())


raw_folder = Path(__file__).resolve().parent
clean_folder = raw_folder.parent / "clean"
review_folder = raw_folder.parent / "review"
projects_file = clean_folder / "Projects.csv"
if not projects_file.is_file():
    raise FileNotFoundError(
        f"Save your cleaned Projects.csv here first: {projects_file}")

# 1. Read the original text. Keep the CSV row numbers for tracing problems.
raw = pn.read_csv(raw_folder / "Tasks.csv",
                  dtype="string", keep_default_na=False)
raw.index = raw.index + 2  # The header is row 1.
projects = pn.read_csv(projects_file, dtype="string")
project_ids = projects["ProjectID"].str.strip().str.upper().dropna()

# 2. Remove extra copies only when all original columns match.
exact_copy = raw.duplicated()
tasks = raw.loc[~exact_copy].copy()
for column in tasks.columns:
    tasks[column] = tasks[column].str.strip()

# 3. Standardise identifiers and stage names.
tasks["TaskID"] = tasks["TaskID"].str.upper()
tasks["ProjectID"] = tasks["ProjectID"].str.upper()
tasks["Stage"] = tasks["Stage"].str.capitalize().replace(
    "Procuremnt", "Procurement")
stages = ["Design", "Approvals", "Procurement",
          "Structure", "Fit-out", "Handover"]

# 4. Parse the three date formats used in this source. Slash dates are day-first.
actual_end_supplied = tasks["ActualEnd"].ne("")
for column in ["PlannedStart", "PlannedEnd", "ActualEnd", "SnapshotDate"]:
    values = tasks[column]
    dates = pn.to_datetime(values, format="%Y-%m-%d", errors="coerce")
    for date_format in ["%d/%m/%Y", "%d-%b-%Y"]:
        dates = dates.fillna(pn.to_datetime(
            values, format=date_format, errors="coerce"))
    tasks[column] = dates

# 5. Store completion as a fraction. For example, both 80% and 0.8 become 0.8.
values = tasks["Completion"]
has_percent = values.str.endswith("%")
completion = pn.to_numeric(values.str.removesuffix("%"), errors="coerce")
tasks["Completion"] = completion.where(~has_percent, completion / 100)

# 6. Read AED budgets as exact decimals, including values such as AED 172,000.00.
amounts = tasks["TaskBudget"].str.removeprefix("AED").str.strip()
valid_amount = amounts.str.fullmatch(
    r"-?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]{1,2})?")
budgets = amounts.where(valid_amount).str.replace(",", "", regex=False)
tasks["TaskBudget"] = budgets.map(
    lambda x: Decimal(x) if pn.notna(x) else None)

# 7. Record every reason a row needs review. A blank ActualEnd is normal for open work.
checks = {
    "Missing task ID": tasks["TaskID"].eq(""),
    "Repeated task ID with different source values": tasks["TaskID"].ne("") & tasks["TaskID"].duplicated(keep=False),
    "Project ID missing from clean Projects": ~tasks["ProjectID"].isin(project_ids),
    "Unknown or missing stage": ~tasks["Stage"].isin(stages),
    "Invalid or missing planned start": tasks["PlannedStart"].isna(),
    "Invalid or missing planned end": tasks["PlannedEnd"].isna(),
    "Planned end before planned start": tasks["PlannedEnd"] < tasks["PlannedStart"],
    "Missing or incorrect snapshot date": tasks["SnapshotDate"].ne(pn.Timestamp("2026-11-22")),
    "Missing or invalid completion": ~tasks["Completion"].between(0, 1).fillna(False),
    "Missing, invalid or nonpositive budget": ~tasks["TaskBudget"].gt(0),
    "Invalid actual end date": actual_end_supplied & tasks["ActualEnd"].isna(),
    "Completed task missing actual end": tasks["Completion"].eq(1) & ~actual_end_supplied,
    "Unfinished task has an actual end": tasks["Completion"].lt(1) & actual_end_supplied,
    "Actual end after snapshot": tasks["ActualEnd"] > tasks["SnapshotDate"],
}
reasons = pn.Series("", index=tasks.index, dtype="string")
for reason, failed in checks.items():
    reasons.loc[failed.fillna(False)] += reason + "; "

# 8. Export accepted rows and a separate review file with the original values.
needs_review = reasons.ne("")
clean = tasks.loc[~needs_review].copy()
review = raw.loc[reasons.index[needs_review]].copy()
review.insert(0, "SourceCSVRow", review.index)
review["Reason"] = reasons.loc[review.index].str.removesuffix("; ")

assert clean["TaskID"].is_unique
assert len(raw) == int(exact_copy.sum()) + len(review) + len(clean)
clean_folder.mkdir(exist_ok=True)
review_folder.mkdir(exist_ok=True)
output = clean_folder / "Tasks.csv"
clean.to_csv(output, index=False, date_format="%Y-%m-%d")
review.to_csv(review_folder / "Tasks_review.csv", index=False)

# 9. Load the saved clean file back into Python and check the exported row count.
saved_tasks = pn.read_csv(output, dtype={"TaskID": "string", "ProjectID": "string"},
                          parse_dates=["PlannedStart", "PlannedEnd", "ActualEnd", "SnapshotDate"])
assert len(saved_tasks) == len(clean)
print(f"Raw rows: {len(raw):,}")
print(f"Exact extra copies removed: {exact_copy.sum():,}")
print(f"Rows sent for review: {len(review):,}")
print(f"Clean rows saved and reloaded: {len(saved_tasks):,}")
print(f"Clean file: {output}")
print(f"Review file: {review_folder / 'Tasks_review.csv'}")
print(saved_tasks.head().to_string(index=False))
