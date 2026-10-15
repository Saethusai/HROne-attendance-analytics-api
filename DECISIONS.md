# DECISIONS.md

1. **Indexes.** I use a unique `emp_code` index and indexes on `department` and `joined_on` for employees. Attendance logs use a unique `(emp_code, date)` index to prevent duplicate daily records, `(date DESC, emp_code ASC)` for attendance listing, and `emp_code` for employee-based lookups. These indexes target the API's actual filters and ordering.

2. **Punch-in race.** Concurrent requests can both pass a check-then-insert test. The unique `(emp_code, date)` index makes the database enforce uniqueness atomically. The losing request receives `DuplicateKeyError`, which the API converts to HTTP 409.

3. **Leaderboard ties.** Results are sorted by total late minutes descending and employee code ascending. Employees with equal totals receive the same rank, and all employees within the requested rank limit are included.

4. **Zero-log employees.** Department summaries start from employees who joined by month-end and use a lookup for attendance logs. Preserving employees without matching logs ensures they still contribute to headcount.

5. **Scaling.** With substantially more data, I would benchmark query patterns before selecting a shard key. Date-range analytics and employee-specific operations may have different distribution needs; indexes and realistic load tests should guide the design.