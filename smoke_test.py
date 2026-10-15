"""
Smoke test for the HROne attendance API.
Run AFTER the server is running: uvicorn app.main:app --port 8000
And AFTER seeding:               python sample_seed.py
"""
import requests
import sys

BASE = "http://localhost:8000"
OK = 0
FAIL = 0


def check(label, resp, expected_status, check_fn=None):
    global OK, FAIL
    passed = resp.status_code == expected_status
    if passed and check_fn:
        try:
            check_fn(resp.json())
        except Exception as e:
            passed = False
            print(f"  [FAIL] {label}: body check failed → {e}")
    if passed:
        OK += 1
        print(f"  [OK]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}: HTTP {resp.status_code}  {resp.text[:250]}")


# ─────────────────────────────────────────────────────────────────────────────
# Epoch ms helpers  (all verified against IST = UTC+5:30)
# 2026-08-03 09:35 IST = 2026-08-03T04:05:00Z  → epoch ms
import datetime, calendar as _cal
def ist_to_ms(year, month, day, hour, minute, second=0):
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    dt  = datetime.datetime(year, month, day, hour, minute, second, tzinfo=ist)
    return int(dt.timestamp() * 1000)

# 2026-08-03 09:35 IST  (EMP9901 shift 09:30-18:30, Mon-Fri)
PI_MS  = ist_to_ms(2026, 8, 3, 9, 35)   # 5 min after shift_start → within grace → late=0
PO_MS  = ist_to_ms(2026, 8, 3, 18, 45)  # 15 min after shift_end → < 30 min → overtime=0
# 2026-07-06 09:30 IST = shift_start exactly (late=0) for EMP0003 regularize test
REG_PI = ist_to_ms(2026, 7, 6, 9, 30)

# ─────────────────────────────────────────────────────────────────────────────
print("=== PRE-CLEAN (remove EMP9901 test data from previous runs) ===")
import os
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv()
_client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), tz_aware=True)
_db = _client[os.getenv("MONGO_DB", "attendance_db")]
_db.employees.delete_many({"emp_code": "EMP9901"})
_db.attendance_logs.delete_many({"emp_code": "EMP9901"})
print("  cleaned EMP9901 test data\n")

# ─────────────────────────────────────────────────────────────────────────────
print("--- HEALTH ---")
check("health ok", requests.get(f"{BASE}/health"), 200,
      lambda b: b["status"] == "ok")

# ─────────────────────────────────────────────────────────────────────────────
print("\n--- EMPLOYEES ---")
emp_payload = {
    "emp_code": "EMP9901", "name": "Test User", "email": "test@example.com",
    "department": "QA", "shift_start": "09:30", "shift_end": "18:30",
    "joined_on": "2026-01-01",
}
r = requests.post(f"{BASE}/employees", json=emp_payload)
check("create employee 201", r, 201,
      lambda b: b["emp_code"] == "EMP9901" and isinstance(b["created_at"], int)
                and "_id" not in b)
check("create dupe 409",
      requests.post(f"{BASE}/employees", json=emp_payload), 409)
check("create invalid emp_code 422",
      requests.post(f"{BASE}/employees",
                    json={**emp_payload, "emp_code": "BAD123"}), 422)
check("create shift_start==shift_end 422",
      requests.post(f"{BASE}/employees",
                    json={**emp_payload, "emp_code": "EMP9902",
                          "shift_start": "09:30", "shift_end": "09:30"}), 422)

r = requests.get(f"{BASE}/employees?page=1&page_size=3")
check("list employees page=1 shape", r, 200,
      lambda b: b["page"] == 1 and b["page_size"] == 3
                and isinstance(b["items"][0].get("created_at"), int))

r = requests.get(f"{BASE}/employees")
check("list employees sorted by emp_code ASC", r, 200,
      lambda b: [e["emp_code"] for e in b["items"]] ==
                sorted(e["emp_code"] for e in b["items"]))

r = requests.get(f"{BASE}/employees?department=Engineering")
check("list employees dept filter", r, 200,
      lambda b: all(e["department"] == "Engineering" for e in b["items"])
                and b["total"] == len([e for e in b["items"] if e["department"] == "Engineering"]) + (b["total"] - len(b["items"])))

# Pagination correctness
r1 = requests.get(f"{BASE}/employees?page=1&page_size=3").json()
r2 = requests.get(f"{BASE}/employees?page=2&page_size=3").json()
if r1["items"] != r2["items"]:
    OK += 1; print("  [OK]   pagination page=2 differs from page=1")
else:
    FAIL += 1; print("  [FAIL] pagination: page=2 returned same as page=1")

# ─────────────────────────────────────────────────────────────────────────────
print("\n--- PUNCH-IN ---")
check("punch-in unknown emp 404",
      requests.post(f"{BASE}/attendance/punch-in",
                    json={"emp_code": "EMPXXXX"}), 404)
check("punch-in bad status 422",
      requests.post(f"{BASE}/attendance/punch-in",
                    json={"emp_code": "EMP9901", "status": "ABSENT"}), 422)
check("punch-in seconds-range epoch 422",
      requests.post(f"{BASE}/attendance/punch-in",
                    json={"emp_code": "EMP9901", "punched_at": 1_000_000}), 422)

r = requests.post(f"{BASE}/attendance/punch-in",
                  json={"emp_code": "EMP9901", "punched_at": PI_MS})
check("punch-in 201 correct shape", r, 201,
      lambda b: (b["emp_code"] == "EMP9901"
                 and b["late_minutes"] == 0      # 5 min ≤ 10-min grace → 0
                 and b["punch_out"] is None
                 and b["punch_in"] == PI_MS
                 and "id" not in b))

check("punch-in dupe 409",
      requests.post(f"{BASE}/attendance/punch-in",
                    json={"emp_code": "EMP9901", "punched_at": PI_MS + 60_000}), 409)

# ─────────────────────────────────────────────────────────────────────────────
print("\n--- PUNCH-OUT ---")
r = requests.post(f"{BASE}/attendance/punch-out",
                  json={"emp_code": "EMP9901", "punched_at": PO_MS})
check("punch-out 200 correct shape", r, 200,
      lambda b: b["punch_out"] == PO_MS
                and b["work_hours"] is not None
                and "id" not in b)
check("punch-out overtime <30 min → 0", r, 200,
      lambda b: b["overtime_minutes"] == 0)
check("punch-out half_day false for full day", r, 200,
      lambda b: b["half_day"] is False)
check("punch-out work_hours is float", r, 200,
      lambda b: isinstance(b["work_hours"], float))

# For the dupe test: punch-in EMP9901 on a different date (2026-08-04 Tue)
# then try two punch-outs for that record
PI_MS2 = ist_to_ms(2026, 8, 4, 9, 35)
PO_MS2 = ist_to_ms(2026, 8, 4, 18, 45)
requests.post(f"{BASE}/attendance/punch-in",
              json={"emp_code": "EMP9901", "punched_at": PI_MS2})
requests.post(f"{BASE}/attendance/punch-out",
              json={"emp_code": "EMP9901", "punched_at": PO_MS2})
# Now try a second punch-out for the same closed record -> must be 404 (no open record)
r2 = requests.post(f"{BASE}/attendance/punch-out",
                   json={"emp_code": "EMP9901", "punched_at": PO_MS2 + 1000})
if r2.status_code in (404, 409):
    OK += 1; print("  [OK]   punch-out dupe: correctly rejected (no open record)")
else:
    FAIL += 1; print(f"  [FAIL] punch-out dupe: expected 404/409 got {r2.status_code}")
check("punch-out unknown emp 404",
      requests.post(f"{BASE}/attendance/punch-out",
                    json={"emp_code": "EMPXXXX"}), 404)

# For EMP0006 (open record punch_in: 2026-07-07T04:05:00Z = 1751861100000)
# punched_at in ms that is BEFORE the punch_in → 422
BEFORE_PI = ist_to_ms(2026, 7, 6, 9, 0)  # before EMP0006's punch_in
check("punch-out punched_at before punch_in → 404 (no record before that ts)",
      requests.post(f"{BASE}/attendance/punch-out",
                    json={"emp_code": "EMP0006", "punched_at": BEFORE_PI}), 404)

# ─────────────────────────────────────────────────────────────────────────────
print("\n--- LIST ATTENDANCE ---")
r = requests.get(f"{BASE}/attendance?emp_code=EMP0001")
check("list attendance filter emp_code", r, 200,
      lambda b: all(i["emp_code"] == "EMP0001" for i in b["items"]))

r = requests.get(f"{BASE}/attendance?date_from=2026-07-06&date_to=2026-07-08")
check("list attendance date range inclusive", r, 200,
      lambda b: all("2026-07-06" <= i["date"] <= "2026-07-08" for i in b["items"]))

check("list attendance date_from > date_to → 422",
      requests.get(f"{BASE}/attendance?date_from=2026-07-10&date_to=2026-07-01"), 422)

r = requests.get(f"{BASE}/attendance?page=1&page_size=2")
check("list attendance page_size=2 respected", r, 200,
      lambda b: len(b["items"]) == 2 and b["page_size"] == 2)

r = requests.get(f"{BASE}/attendance")
def check_sort(b):
    items = b["items"]
    for i in range(1, len(items)):
        assert items[i]["date"] <= items[i-1]["date"], \
            f"date not DESC at pos {i}: {items[i]['date']} vs {items[i-1]['date']}"
check("list attendance sort date DESC", r, 200, check_sort)

check("list attendance punch_in is int or null", r, 200,
      lambda b: all(isinstance(i["punch_in"], (int, type(None))) for i in b["items"]))
check("list attendance no _id in items", r, 200,
      lambda b: all("_id" not in i for i in b["items"]))

# ─────────────────────────────────────────────────────────────────────────────
print("\n--- REGULARIZE ---")
# EMP0003 2026-07-06: punch_in was at 04:35 UTC (10:05 IST). Correct to 09:30 IST.
# REG_PI = 2026-07-06 09:30 IST → attendance_date must remain 2026-07-06
r = requests.patch(f"{BASE}/attendance/EMP0003/2026-07-06",
                   json={"reason": "correcting punch_in time",
                         "regularized_by": "hr.admin",
                         "punch_in": REG_PI})
check("regularize 200 and history appended", r, 200,
      lambda b: len(b["history"]) >= 1 and b["history"][-1]["by"] == "hr.admin")
check("regularize history contains punch_in change", r, 200,
      lambda b: "punch_in" in b["history"][-1]["changes"])
check("regularize late_minutes recomputed to 0", r, 200,
      lambda b: b["late_minutes"] == 0)

check("regularize nothing-changed → 422",
      requests.patch(f"{BASE}/attendance/EMP0003/2026-07-06",
                     json={"reason": "no change here",
                           "regularized_by": "hr.admin"}), 422)
check("regularize unknown emp → 404",
      requests.patch(f"{BASE}/attendance/EMPXXXX/2026-07-06",
                     json={"reason": "x" * 5, "regularized_by": "hr"}), 404)
check("regularize ABSENT with punch_in → 422",
      requests.patch(f"{BASE}/attendance/EMP0004/2026-07-08",
                     json={"status": "ABSENT", "punch_in": REG_PI,
                           "reason": "test reason", "regularized_by": "hr"}), 422)
check("regularize unknown record → 404",
      requests.patch(f"{BASE}/attendance/EMP0001/2020-01-01",
                     json={"reason": "no such record",
                           "regularized_by": "hr"}), 404)

# ─────────────────────────────────────────────────────────────────────────────
print("\n--- ANALYTICS: employee monthly ---")
r = requests.get(f"{BASE}/analytics/employees/EMP0001/monthly?month=2026-07")
MONTHLY_FIELDS = ["emp_code","month","working_days","present_days","leave_days",
                  "late_count","total_late_minutes","total_overtime_minutes","attendance_pct"]
check("employee monthly 200 all fields present", r, 200,
      lambda b: all(k in b for k in MONTHLY_FIELDS))
check("employee monthly working_days > 0 for July", r, 200,
      lambda b: b["working_days"] > 0)
check("employee monthly attendance_pct is number or null", r, 200,
      lambda b: isinstance(b["attendance_pct"], (float, int, type(None))))
check("employee monthly unknown emp → 404",
      requests.get(f"{BASE}/analytics/employees/EMPXXXX/monthly?month=2026-07"), 404)

# ─────────────────────────────────────────────────────────────────────────────
print("\n--- ANALYTICS: department summary ---")
r = requests.get(f"{BASE}/analytics/departments/summary?month=2026-07")
DEPT_FIELDS = ["department","headcount","present_days","avg_work_hours",
               "late_count","total_late_minutes","leave_count","on_duty_count"]
check("dept summary 200", r, 200,
      lambda b: "items" in b and len(b["items"]) > 0)
check("dept summary all fields per item", r, 200,
      lambda b: all(all(k in i for k in DEPT_FIELDS) for i in b["items"]))
check("dept summary sorted by department ASC", r, 200,
      lambda b: [i["department"] for i in b["items"]] ==
                sorted(i["department"] for i in b["items"]))
check("dept summary headcount > 0 for all items", r, 200,
      lambda b: all(i["headcount"] > 0 for i in b["items"]))

# ─────────────────────────────────────────────────────────────────────────────
print("\n--- ANALYTICS: leaderboard ---")
r = requests.get(f"{BASE}/analytics/leaderboard/late?month=2026-07")
check("leaderboard 200", r, 200, lambda b: "items" in b)
check("leaderboard only late_minutes > 0", r, 200,
      lambda b: all(i["total_late_minutes"] > 0 for i in b["items"]))
check("leaderboard sorted total_late_minutes DESC", r, 200,
      lambda b: [i["total_late_minutes"] for i in b["items"]] ==
                sorted((i["total_late_minutes"] for i in b["items"]), reverse=True))

def check_ranking(b):
    items = b["items"]
    for i in range(1, len(items)):
        assert items[i]["rank"] >= items[i-1]["rank"], "ranks not non-decreasing"
        if items[i]["total_late_minutes"] < items[i-1]["total_late_minutes"]:
            assert items[i]["rank"] == i + 1, \
                f"gap wrong at pos {i}: got rank {items[i]['rank']} expected {i+1}"
check("leaderboard standard competition ranking", r, 200, check_ranking)

# ─────────────────────────────────────────────────────────────────────────────
print("\n--- ANALYTICS: department trend ---")
r = requests.get(
    f"{BASE}/analytics/departments/Engineering/trend?from=2026-07-01&to=2026-07-10"
)
TREND_FIELDS = ["date","is_working_day","headcount","present_count",
                "late_count","attendance_rate","moving_avg_7d"]
check("dept trend 200 exactly 10 rows", r, 200,
      lambda b: len(b["items"]) == 10)
check("dept trend all required fields present", r, 200,
      lambda b: all(all(k in i for k in TREND_FIELDS) for i in b["items"]))
check("dept trend Mon-Fri marked as working days", r, 200,
      lambda b: all(
          i["is_working_day"] == (
              __import__("datetime").datetime.fromisoformat(i["date"]).weekday() < 5
          ) for i in b["items"]
      ))
check("dept trend attendance_rate null on weekends", r, 200,
      lambda b: all(
          i["attendance_rate"] is None
          for i in b["items"] if not i["is_working_day"]
      ))
check("dept trend to < from → 422",
      requests.get(f"{BASE}/analytics/departments/Engineering/trend?from=2026-07-10&to=2026-07-01"), 422)
check("dept trend > 92 days → 422",
      requests.get(f"{BASE}/analytics/departments/Engineering/trend?from=2026-01-01&to=2026-05-01"), 422)
check("dept trend unknown dept → 404",
      requests.get(f"{BASE}/analytics/departments/UNKNOWNDEPT/trend?from=2026-07-01&to=2026-07-10"), 404)

# ─────────────────────────────────────────────────────────────────────────────
print("\n--- ADMIN EXPLAIN ---")
r = requests.get(f"{BASE}/admin/explain/attendance_list")
check("explain attendance_list 200", r, 200,
      lambda b: "explain" in b and b["collection"] == "attendance_logs"
                and b["endpoint"] == "attendance_list")

r = requests.get(f"{BASE}/admin/explain/employee_monthly?emp_code=EMP0001&month=2026-07")
check("explain employee_monthly 200", r, 200, lambda b: "explain" in b)

r = requests.get(f"{BASE}/admin/explain/department_summary?month=2026-07")
check("explain department_summary 200", r, 200,
      lambda b: "explain" in b and b["collection"] == "employees")

r = requests.get(f"{BASE}/admin/explain/late_leaderboard?month=2026-07")
check("explain late_leaderboard 200", r, 200, lambda b: "explain" in b)

r = requests.get(f"{BASE}/admin/explain/department_trend?department=Engineering&from=2026-07-01&to=2026-07-10")
check("explain department_trend 200", r, 200, lambda b: "explain" in b)

check("explain invalid endpoint → 422",
      requests.get(f"{BASE}/admin/explain/bad_endpoint"), 422)
check("explain employee_monthly missing params → 422",
      requests.get(f"{BASE}/admin/explain/employee_monthly"), 422)

# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*52}")
print(f"  RESULT: {OK} passed,  {FAIL} failed")
print(f"{'='*52}")
sys.exit(0 if FAIL == 0 else 1)
