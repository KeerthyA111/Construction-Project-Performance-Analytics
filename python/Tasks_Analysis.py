from pathlib import Path
import pandas as pn

tasks = pn.read_csv(
    Path(__file__).with_name("Tasks.csv"),
    parse_dates=["PlannedEnd", "ActualEnd", "SnapshotDate"]
)

# Completed tasks are those with a Completion value of 1. Create a new column called FinishedLate that is True if the ActualEnd date is later than the PlannedEnd date.

completed = tasks.loc[tasks["Completion"] == 1].copy()
completed["FinishedLate"] = completed["ActualEnd"] > completed["PlannedEnd"]


# 1. Finished tasks?
def late_finish_summary(group_by):
    Stage_summary = completed.groupby(group_by).agg(
        CompletedTasks=("TaskID", "count"),
        LateTasks=("FinishedLate", "sum")
    )
    Stage_summary["LateRate%"] = (
        100 * Stage_summary["LateTasks"] / Stage_summary["CompletedTasks"]).round(1)
    return Stage_summary.sort_values("LateRate%", ascending=False)


# Save the returned table so you can use it again later
Stage_summary = late_finish_summary("Stage")

# Which stages finish late most often?
print(late_finish_summary("Stage"))
# Which projects finish late most often?
print(late_finish_summary("ProjectID"))
# Which stages within which projects?
print(late_finish_summary(["ProjectID", "Stage"]))

print(Stage_summary.sort_values("LateRate%", ascending=False))

# 2.Which stage had the most unfinished tasks that were already overdue on 22 November 2026?

# Count unfinished tasks whose planned end date has passed
overdue = tasks.loc[
    (tasks["Completion"] < 1) &
    (tasks["PlannedEnd"] < tasks["SnapshotDate"])
]

print("\n")
print("Total overdue tasks:", len(overdue))

print("\n")
print("Overdue tasks by stage:")
print(overdue["Stage"].value_counts())

# Create an analysis folder beside Tasks_Analysis.py, which is in clean
output_folder = Path(__file__).parent / "Analysis"
output_folder.mkdir(exist_ok=True)

# Save the three summaries
Stage_summary.to_csv(output_folder / "Stage_summary.csv")

project_summary = late_finish_summary("ProjectID")
project_summary.to_csv(output_folder / "Project_summary.csv")

project_stage_summary = late_finish_summary(["ProjectID", "Stage"])
project_stage_summary.to_csv(output_folder / "Project_stage_summary.csv")

# Add days overdue to the task detail and save it
overdue = overdue.copy()
overdue["DaysOverdue"] = (overdue["SnapshotDate"] -
                          overdue["PlannedEnd"]).dt.days
overdue.to_csv(output_folder / "Overdue_tasks.csv", index=False)


# How many days overdue are the open tasks?
print(overdue["DaysOverdue"].median())

# Which stage has the longest-standing backlog?
overdue_by_stage = overdue.groupby("Stage").agg(
    OverdueTasks=("TaskID", "count"),
    MedianDaysOverdue=("DaysOverdue", "median")
)

overdue_by_stage = overdue_by_stage.sort_values(
    "MedianDaysOverdue", ascending=False)
print(overdue_by_stage)
overdue_by_stage.to_csv(output_folder / "Overdue_by_stage.csv")

#

if table.name == "Tasks":
    starts = pd.read_csv(
        RAW_FOLDER / "Task_actual_starts.csv",
        dtype={"TaskID": "string"}
    )

    starts["TaskID"] = starts["TaskID"].str.strip().str.upper()
    starts["ActualStart"] = pd.to_datetime(
        starts["ActualStart"], format="%Y-%m-%d", errors="raise"
    )

    clean = clean.merge(
        starts[["TaskID", "ActualStart"]],
        on="TaskID",
        how="left",
        validate="one_to_one"
    )
