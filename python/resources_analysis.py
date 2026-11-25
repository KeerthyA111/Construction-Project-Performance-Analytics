"""Compare weekly assigned hours with each employee's available hours."""

from pathlib import Path
import pandas as pn

folder = Path(__file__).parent

assignments = pn.read_csv(folder / "Assignments.csv")
capacity = pn.read_csv(folder / "Capacity.csv")

print((folder / "Assignments.csv").resolve())
print(assignments.columns.tolist())

# 2. Add up the assigned hours for each employee and week
weekly_assigned = (
    assignments.groupby(["EmployeeID", "WeekStart"], as_index=False)
    .agg(AssignedHours=("AssignedHours", "sum"))
)

print(weekly_assigned.head())


# which employees have more work assigned than they have hours available in a given week.

# Match each employee's weekly capacity with their total assigned hours
workload = capacity.merge(
    weekly_assigned,
    on=["EmployeeID", "WeekStart"],
    how="left",
    validate="one_to_one"
)

# A week with no matching assignment has zero recorded assigned hours
workload["AssignedHours"] = workload["AssignedHours"].fillna(0)

# Calculate how many hours are still available
workload["RemainingHours"] = workload["AvailableHours"] - \
    workload["AssignedHours"]

# Show the most overloaded employee-weeks first
overloaded = workload.loc[workload["RemainingHours"] < 0]
print(overloaded.sort_values("RemainingHours").head(10))


# which employees are overbooked, in which weeks, and by how many hours.
workload["RemainingHours"] = (
    workload["AvailableHours"] - workload["AssignedHours"]
).round(2)

# Show the 10 most overbooked employee-weeks.
print("\n")
print('Show the 10 most overbooked employee-weeks.')
overloaded = workload.loc[workload["RemainingHours"] < 0]
print(overloaded.sort_values("RemainingHours").head(10))
# .loc[...] keeps the rows where remaining hours are negative. Sorting puts -12 before -8, so the biggest shortage appears first.


print("\n")

# 3. Count how many employees are affected.

print("Overbooked employee-weeks:", len(overloaded))
print("Distinct employees overbooked:", overloaded["EmployeeID"].nunique())

print("Done")

# Which week has the most overbooked hours?
overloaded = workload.loc[workload["RemainingHours"] < 0]
weekly_shortage = (
    overloaded.groupby("WeekStart")["RemainingHours"]
    .sum()
    .abs()
    .sort_values(ascending=False)
)

print(weekly_shortage.head())
if weekly_shortage.empty:
    print("No employees were overbooked in any week.")
else:
    week = weekly_shortage.index[0]
    hours = weekly_shortage.iloc[0]

    print(
        f"The week beginning {week} had the largest staffing imbalance, "
        f"with {hours:,.2f} assigned hours above individual employees’ capacity."
    )
# whether other employees had enough spare hours that same week to cover the gap

    spare = workload.loc[
        (workload["WeekStart"] == week) & (workload["RemainingHours"] > 0)
    ]
    spare_hours = spare["RemainingHours"].sum()

    print(f"Overbooked hours: {hours:,.2f}")
    print(f"Spare hours in the same week: {spare_hours:,.2f}")
    print(spare.nlargest(5, "RemainingHours")
          [["EmployeeID", "RemainingHours"]])
