from decimal import Decimal
from pathlib import Path
from shutil import copy2
from tempfile import TemporaryDirectory

import pandas as pd


RAW_FOLDER = Path(__file__).resolve().parent
SNAPSHOT = pd.Timestamp("2026-11-22")
FIRST_WEEK = pd.Timestamp("2026-11-23")
LAST_WEEK = pd.Timestamp("2027-02-08")
CITIES = ["Dubai", "Abu Dhabi", "Sharjah"]
WEEK_KEY = ["EmployeeID", "WeekStart"]


# Shared steps: load original text, record row numbers, trim spaces and check keys.
class Table:
    def __init__(self, name):
        self.name = name
        self.raw = pd.read_csv(RAW_FOLDER / f"{name}.csv", dtype="string",
                               keep_default_na=False, encoding="utf-8-sig")
        self.raw.index += 2  # The header is the first row of the CSV.
        exact_copy = self.raw.duplicated()
        self.duplicates = int(exact_copy.sum())
        self.data = self.raw.loc[~exact_copy].copy()
        for column in self.data:
            values = self.data[column].str.strip()
            self.data[column] = values.str.upper(
            ) if column.endswith("ID") else values
        self.reasons = pd.Series("", index=self.data.index, dtype="string")

    def flag(self, condition, reason):
        self.reasons.loc[condition.fillna(False)] += reason + "; "

    def check_key(self, columns):
        values = self.data[columns]
        missing = (values.isna() | values.eq("")).any(axis=1)
        repeated = ~missing & self.data.duplicated(columns, keep=False)
        self.flag(missing, "Missing key field")
        self.flag(repeated, "Repeated key with different original records")

    def clean_rows(self):
        return self.data.loc[self.reasons.eq("")]

    def review_rows(self):
        reasons = self.reasons.loc[self.reasons.ne("")]
        rows = self.raw.loc[reasons.index].copy()
        rows.insert(0, "SourceCSVRow", rows.index)
        rows["Reason"] = reasons.str.removesuffix("; ")
        return rows


def dates(values):
    parsed = pd.to_datetime(values, format="%Y-%m-%d", errors="coerce")
    for date_format in ["%d/%m/%Y", "%d-%b-%Y"]:
        alternate = pd.to_datetime(values, format=date_format, errors="coerce")
        parsed = parsed.fillna(alternate)
    return parsed


def money(values):
    # Accept a plain or correctly grouped AED amount with at most two decimal places.
    text = values.str.upper().str.removeprefix("AED").str.strip()
    valid = text.str.fullmatch(
        r"-?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]{1,2})?")
    text = text.where(valid).str.replace(",", "", regex=False)
    return text.map(lambda value: Decimal(value) if pd.notna(value) else None)


def hours(values):
    numeric = values.str.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")
    return pd.to_numeric(values.where(numeric), errors="coerce")


def check_week(table):
    week = dates(table.data["WeekStart"])
    table.data["WeekStart"] = week
    valid = week.between(FIRST_WEEK, LAST_WEEK) & week.dt.dayofweek.eq(0)
    table.flag(~valid, "WeekStart must be a Monday in the 12-week planning window")


def clean_projects():
    table = Table("Projects")
    data = table.data
    data["Location"] = data["Location"].str.title().replace("Dxb", "Dubai")
    data["Currency"] = data["Currency"].str.upper()
    data["ProjectType"] = data["ProjectType"].str.title()
    types = ["Residential", "Commercial",
             "Warehouse", "Healthcare", "Education"]
    table.check_key(["ProjectID"])
    table.flag(data["ProjectName"].eq(""), "Missing project name")
    table.flag(~data["Location"].isin(CITIES), "Unknown project location")
    table.flag(data["Currency"].ne("AED"), "Missing or unexpected currency")
    table.flag(~data["ProjectType"].isin(types), "Unknown project type")
    return table


def clean_employees():
    table = Table("Employees")
    data = table.data
    data["Role"] = data["Role"].str.title().replace({
        "Civil Eng.": "Civil Engineer", "Mep Engineer": "MEP Engineer"
    })
    data["BaseLocation"] = data["BaseLocation"].str.title().replace("Dxb",
                                                                    "Dubai")
    roles = ["Civil Engineer", "MEP Engineer", "Technician", "Supervisor",
             "Planner", "Quantity Surveyor"]
    table.check_key(["EmployeeID"])
    table.flag(~data["Role"].isin(roles), "Missing or unknown employee role")
    table.flag(~data["BaseLocation"].isin(CITIES),
               "Unknown employee base location")
    return table


def clean_tasks(projects):
    table = Table("Tasks")
    data = table.data
    data["Stage"] = data["Stage"].str.capitalize().replace(
        "Procuremnt", "Procurement")
    stages = ["Design", "Approvals", "Procurement",
              "Structure", "Fit-out", "Handover"]
    actual_end_supplied = data["ActualEnd"].ne("")
    for column in ["PlannedStart", "PlannedEnd", "ActualEnd", "SnapshotDate"]:
        data[column] = dates(data[column])
    progress = data["Completion"]
    fraction = pd.to_numeric(progress.str.removesuffix("%"), errors="coerce")
    data["Completion"] = fraction.where(
        ~progress.str.endswith("%"), fraction / 100)
    data["TaskBudget"] = money(data["TaskBudget"])

    table.check_key(["TaskID"])
    table.flag(~data["ProjectID"].isin(projects["ProjectID"]),
               "ProjectID absent from clean Projects")
    table.flag(~data["Stage"].isin(stages), "Unknown task stage")
    table.flag(data["PlannedStart"].isna(), "Missing or invalid planned start")
    table.flag(data["PlannedEnd"].isna(), "Missing or invalid planned end")
    table.flag(data["PlannedEnd"] < data["PlannedStart"],
               "Planned end before planned start")
    table.flag(data["SnapshotDate"].ne(SNAPSHOT),
               "Missing or incorrect snapshot date")
    table.flag(~data["Completion"].between(0, 1).fillna(
        False), "Missing or invalid completion")
    table.flag(~data["TaskBudget"].gt(
        0), "Budget must be a positive AED amount")
    table.flag(actual_end_supplied &
               data["ActualEnd"].isna(), "Invalid actual end")
    table.flag(~actual_end_supplied & data["Completion"].eq(
        1), "Completed task missing actual end")
    table.flag(actual_end_supplied & data["Completion"].lt(
        1), "Unfinished task has an actual end")
    table.flag(data["ActualEnd"] > data["SnapshotDate"],
               "Actual end after snapshot")
    return table


def clean_capacity(employees):
    table = Table("Capacity")
    data = table.data
    check_week(table)
    table.check_key(WEEK_KEY)
    data["AvailableHours"] = hours(data["AvailableHours"])
    table.flag(~data["EmployeeID"].isin(employees["EmployeeID"]),
               "EmployeeID absent from clean Employees")
    # Zero is valid. A single person has at most 7 x 24 hours in one calendar week.
    table.flag(~data["AvailableHours"].between(0, 7 * 24).fillna(False),
               "Available hours missing, invalid or outside 0 to 168")
    return table


def clean_assignments(projects, employees, capacity):
    table = Table("Assignments")
    data = table.data
    check_week(table)
    table.check_key(["AssignmentID"])
    data["PlannedHours"] = hours(data["PlannedHours"])
    table.flag(~data["PlannedHours"].ge(0).fillna(False),
               "Missing, invalid or negative planned hours")
    table.flag(~data["ProjectID"].isin(projects["ProjectID"]),
               "ProjectID absent from clean Projects")
    table.flag(~data["EmployeeID"].isin(employees["EmployeeID"]),
               "EmployeeID absent from clean Employees")
    # Multiple assignments can legitimately match one employee-week.
    assigned_weeks = pd.MultiIndex.from_frame(data[WEEK_KEY])
    available_weeks = pd.MultiIndex.from_frame(capacity[WEEK_KEY])
    missing_week = pd.Series(~assigned_weeks.isin(
        available_weeks), index=data.index)
    table.flag(missing_week, "Employee and week absent from clean Capacity")
    return table


def clean_costs(tasks):
    table = Table("Costs")
    data = table.data
    data["Category"] = data["Category"].str.capitalize()
    data["EntryType"] = data["EntryType"].str.capitalize()
    data["ActualCost"] = money(data["ActualCost"])
    data["CostDate"] = dates(data["CostDate"])
    categories = ["Labour", "Materials", "Equipment", "Subcontractor"]
    charge = data["EntryType"].eq("Charge")
    credit = data["EntryType"].eq("Credit")

    table.check_key(["CostID"])
    table.flag(~data["TaskID"].isin(tasks["TaskID"]),
               "TaskID absent from clean Tasks")
    table.flag(~data["Category"].isin(categories), "Unknown cost category")
    table.flag(~(charge | credit), "Unknown entry type")
    table.flag(data["CostDate"].isna() | data["CostDate"].gt(
        SNAPSHOT), "Invalid cost date or after cutoff")
    table.flag(charge & ~data["ActualCost"].gt(
        0), "Charge must have a positive amount")
    table.flag(credit & ~data["ActualCost"].lt(
        0), "Credit must have a negative amount")
    table.flag(charge & data["ReversalOfCostID"].ne(
        ""), "Charge has a reversal reference")

    # Look up the referenced charge after its own checks, regardless of CSV row order.
    charges = data.loc[charge & table.reasons.eq("")].set_index("CostID")
    reference = data["ReversalOfCostID"]
    linked = credit & reference.isin(charges.index)
    table.flag(credit & ~linked, "Credit has no matching clean charge")
    for column in ["TaskID", "Category"]:
        table.flag(linked & data[column].ne(reference.map(charges[column])),
                   f"Credit and original charge have different {column}")
    table.flag(linked & data["CostDate"].lt(reference.map(charges["CostDate"])),
               "Credit date before original charge")
    return table


def write_outputs(tables, root):
    # Build and reload every CSV before replacing existing outputs. If a file is
    # locked (for example, open in Excel on Windows), roll back this batch.
    summary = []
    with TemporaryDirectory(dir=root) as temp:
        stage = Path(temp)
        (stage / "clean").mkdir()
        (stage / "review").mkdir()
        for table in tables:
            clean = table.clean_rows()
            review = table.review_rows()
            clean_path = stage / "clean" / f"{table.name}.csv"
            clean.to_csv(clean_path, index=False, date_format="%Y-%m-%d")
            review.to_csv(stage / "review" /
                          f"{table.name}_review.csv", index=False)
            saved = pd.read_csv(clean_path, dtype="string",
                                keep_default_na=False)
            if len(saved) != len(clean) or list(saved.columns) != list(clean.columns):
                raise ValueError(
                    f"Could not verify the exported {table.name} table")
            if len(table.raw) != table.duplicates + len(review) + len(clean):
                raise ValueError(
                    f"Row counts do not reconcile for {table.name}")
            summary.append([table.name, len(table.raw),
                           table.duplicates, len(review), len(clean)])

        counts = pd.DataFrame(summary, columns=["Table", "RawRows", "ExactCopiesRemoved",
                                                "ReviewRows", "CleanRows"])
        counts.to_csv(stage / "review" / "Cleaning_summary.csv", index=False)
        replacements = []
        try:
            for source in sorted(stage.glob("*/*.csv")):
                target = root / source.relative_to(stage)
                target.parent.mkdir(exist_ok=True)
                backup = None
                if target.exists():
                    backup = stage / (source.parent.name +
                                      "_" + source.name + ".bak")
                    copy2(target, backup)
                source.replace(target)
                replacements.append((target, backup))
        except OSError:
            for target, backup in reversed(replacements):
                if backup is None:
                    target.unlink()
                else:
                    backup.replace(target)
            raise
    return counts


def main():
    # Clean parent tables first so child records can be checked against accepted keys.
    projects = clean_projects()
    employees = clean_employees()
    tasks = clean_tasks(projects.clean_rows())
    capacity = clean_capacity(employees.clean_rows())
    assignments = clean_assignments(
        projects.clean_rows(), employees.clean_rows(), capacity.clean_rows())
    costs = clean_costs(tasks.clean_rows())
    tables = [projects, employees, tasks, capacity, assignments, costs]
    root = RAW_FOLDER.parent
    counts = write_outputs(tables, root)
    print(counts.to_string(index=False))
    print("Clean files:", root / "clean")
    print("Rows to review and summary:", root / "review")


if __name__ == "__main__":
    main()
