alter table dbo.Assignments
Alter column weekstart date not null;

ALTER TABLE dbo.Assignments
ALTER COLUMN AssignedHours decimal(18,10) NOT NULL;



Select top (10)* 
 from Costs;

--1 — Calculate net recorded cost per task
Select TaskID,  sum(ActualCost) as NetRecord, max(CostDate) as LastCostDate
From Costs
where CostDate<= '2026-02-01'
Group by taskID;

--2 — Which completed tasks went over budget, and by how much?
--You’ve calculated one spending total per task. Now match that total to TaskBudget from the Tasks table.

--Select Top (10)* from Tasks


With CostPerTask_CTE as ( select TaskID,  
						sum(ActualCost) as NetRecord
						From Costs
						Group by taskID)

Select c.TaskID, c.NetRecord, t.TaskBudget, c.NetRecord-t.TaskBudget as OverBudget
From Tasks as t
Join CostPerTask_CTE as C
on t.TaskID = c.TaskID

where t.Completion=1
and c.NetRecord> t.TaskBudget

Order by OverBudget Desc;


-- 3. Which projects have the largest total overruns on completed tasks?

;WITH CostPerTask_CTE AS (
    SELECT
        TaskID,
        SUM(ActualCost) AS NetRecordedCost
    FROM Costs
    GROUP BY TaskID
)
SELECT
    p.ProjectID,
    p.ProjectName,
    COUNT(t.TaskID) AS CompletedTasks,
    COUNT(c.TaskID) AS CompletedTasksWithCosts,
    COUNT(CASE
        WHEN c.NetRecordedCost > t.TaskBudget THEN 1
    END) AS OverBudgetTasks,
    SUM(CASE
        WHEN c.NetRecordedCost > t.TaskBudget
            THEN c.NetRecordedCost - t.TaskBudget
        ELSE 0
    END) AS TotalOverrunAED

FROM Projects AS p

LEFT JOIN Tasks AS t
    ON p.ProjectID = t.ProjectID
    AND t.Completion = 1
LEFT JOIN CostPerTask_CTE AS c
    ON t.TaskID = c.TaskID
GROUP BY p.ProjectID, p.ProjectName
ORDER BY TotalOverrunAED DESC, p.ProjectID;





--4 — Which completed tasks finished late and also went over budget?
SELECT t.Projectid, 
	   t.Taskid, 
	   t.stage,
	   DATEDIFF (day, PlannedEnd, ActualEnd) as DaysLate,
	   t.taskbudget,
	   cpt.NETactualcost,
	   cpt.NetActualCost - t.TaskBudget AS OverrunAED

from tasks as t
left join CostPerTask as cpt
on cpt.TaskID = t.taskID

where Completion=1
AND t.ActualEnd > t.PlannedEnd
AND cpt.NetActualCost > t.TaskBudget
ORDER BY DaysLate DESC,OverrunAED DESC ;

Select top(10) * from CostPerTask;

--5 - Which projects have the largest total overrun from tasks that finished both late and over budget?

SELECT
    t.ProjectID,
    COUNT(*) AS LateOverBudgetTasks,
    SUM(cpt.NetActualCost - t.TaskBudget) AS TotalOverrunAED,
    MAX(DATEDIFF(day, t.PlannedEnd, t.ActualEnd)) AS LongestDelayDays
FROM dbo.Tasks AS t
JOIN dbo.CostPerTask AS cpt
    ON cpt.TaskID = t.TaskID
WHERE t.Completion = 1
  AND t.ActualEnd > t.PlannedEnd
  AND cpt.NetActualCost > t.TaskBudget
GROUP BY t.ProjectID
ORDER BY TotalOverrunAED DESC, t.ProjectID;


--6 — Which projects are still over budget on completed work after you include the tasks that came in under budget?
SELECT
    t.ProjectID,
    COUNT(t.TaskID) AS CompletedTasks,
    COUNT(cpt.TaskID) AS CompletedTasksWithCost,
    SUM(cpt.NetActualCost - t.TaskBudget) AS NetVarianceAED
FROM dbo.Tasks AS t
LEFT JOIN CostPerTask AS cpt
    ON cpt.TaskID = t.TaskID
WHERE t.Completion = 1
GROUP BY t.ProjectID
HAVING SUM(cpt.NetActualCost - t.TaskBudget) > 0
ORDER BY NetVarianceAED DESC;

-- 7- Which projects had the most unfinished tasks past their planned end date on the review date?

		select projectid,
			   count (taskID) as unfinished_task

		from Tasks  
		where SnapshotDate = (SELECT MAX(SnapshotDate) FROM dbo.Tasks)
		and completion<1
		and plannedend<SnapshotDate
		group by projectid
		order by unfinished_task desc;

-- 8 - Which project has the task that has been overdue the longest as of the latest review date?

SELECT
    p.ProjectID,
    COUNT(t.TaskID) AS OverdueTasks,
    MAX(DATEDIFF(day, t.PlannedEnd, t.SnapshotDate)) AS MaxDaysOverdue
FROM Projects AS p
JOIN Tasks AS t
    ON t.ProjectID = p.ProjectID
WHERE t.SnapshotDate = (SELECT MAX(SnapshotDate) FROM Tasks)
  AND t.Completion < 1
  AND t.PlannedEnd < t.SnapshotDate
GROUP BY p.ProjectID
ORDER BY MaxDaysOverdue DESC;	


-- Which employees were assigned more hours than they had available in the week starting 7 December 2026, and by how many hours?
SELECT
    a.EmployeeID,
    a.WeekStart,
    SUM(a.AssignedHours) AS TotalAssignedHours,
    c.AvailableHours,
    SUM(a.AssignedHours) - c.AvailableHours AS HoursOverCapacity
FROM Assignments AS a
JOIN Capacity AS c
    ON a.EmployeeID = c.EmployeeID
   AND a.WeekStart = c.WeekStart
WHERE a.WeekStart = '20261207'
GROUP BY a.EmployeeID, a.WeekStart, c.AvailableHours
HAVING SUM(a.AssignedHours) > c.AvailableHours
ORDER BY HoursOverCapacity DESC;
