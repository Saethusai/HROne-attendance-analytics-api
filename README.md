# HROne Attendance Tracking API

FastAPI + MongoDB attendance tracking REST API built for the HROne engineering assignment.

## Setup

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
```

**Windows (Command Prompt):**
```bat
.venv\Scripts\activate
```

**macOS / Linux:**
```bash
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Set the MongoDB connection details before starting the application.

**Windows (Command Prompt):**
```bat
set MONGO_URI=mongodb://localhost:27017
set MONGO_DB=attendance_db
```

**macOS / Linux:**
```bash
export MONGO_URI=mongodb://localhost:27017
export MONGO_DB=attendance_db
```

For MongoDB Atlas, set `MONGO_URI` to your Atlas connection string. Do not commit credentials or secrets.

### 4. Seed sample data (optional)

Ensure MongoDB is running and configured before executing:

```bash
python sample_seed.py
```

This script inserts the project's sample employee and attendance records into MongoDB. Run it only when you want to populate the sample dataset.

### 5. Start the server

```bash
uvicorn app.main:app --port 8000
```

The application should create its required indexes at startup.

MongoDB 6.0 or newer is required; the assignment grader uses MongoDB 7.0. MongoDB Atlas free tier or a local MongoDB instance can be used.

To start MongoDB locally with Docker, if Docker is installed:

```bash
docker run -p 27017:27017 mongo:7
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MONGO_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGO_DB` | `attendance_db` | Database name |

## API Documentation

Once the server is running, interactive API documentation is available at:

- Swagger UI: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | MongoDB readiness probe |
| POST | `/employees` | Create an employee |
| GET | `/employees` | List employees (paginated) |
| POST | `/attendance/punch-in` | Record punch-in |
| POST | `/attendance/punch-out` | Record punch-out |
| GET | `/attendance` | List attendance records |
| PATCH | `/attendance/{emp_code}/{date}` | Regularize an attendance record |
| GET | `/analytics/employees/{emp_code}/monthly` | Employee monthly summary |
| GET | `/analytics/departments/summary` | Department summary |
| GET | `/analytics/leaderboard/late` | Late-comers leaderboard |
| GET | `/analytics/departments/{department}/trend` | Daily department attendance trend |
| GET | `/admin/explain/{endpoint}` | MongoDB query execution plan |

## Submission Checklist

Submit a public Git repository containing the required source code and documentation, including:

- `app/main.py`
- `requirements.txt`
- `README.md`
- `REVIEW.md`
- `DECISIONS.md`
- `sample_seed.py` (if used to seed the sample data)

Do not commit `.env` files, credentials, secrets, virtual environments, or unnecessary generated files.

Do not include a Dockerfile if the assignment submission instructions prohibit it.