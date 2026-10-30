# MP2 REST API

A FastAPI application for uploading CSV files, retrieving stored rows, and processing
datasets with the reusable MP1 validation and cleaning modules. Uploaded pandas
DataFrames are stored as copies in memory with sequential IDs. A processing request
validates numeric values, applies configurable duplicate, missing-value, and outlier
handling, returns a report, and replaces the stored dataset only after success.
Request middleware records an ID, method, path, status, and duration for each request
and returns the ID in an `X-Request-ID` response header. The application preserves
MP1's logging format and includes automated API, storage, model, and middleware tests.

## Setup (Windows PowerShell)

Run these commands from the repository root. Tested with Python 3.13.7.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

For later sessions, activate the existing environment. You can also call
`.\venv\Scripts\python.exe` directly in place of `python` without activating it.

## Run

```powershell
python -m uvicorn main:app --reload
```

Open [Swagger UI](http://127.0.0.1:8000/docs) to exercise the API.

| Method | Endpoint | Behavior |
| --- | --- | --- |
| GET | `/health` | Return `{"status": "ok", "version": "1.0.0"}`. |
| POST | `/upload` | Accept a multipart `file` field containing CSV and return dataset metadata. |
| GET | `/datasets/{dataset_id}?limit=100` | Return the first rows in their stored order and the full `total_rows` count. |
| POST | `/datasets/{dataset_id}/process` | Validate and clean the dataset using a JSON configuration, replace stored data, and return a report. |

Successful requests return 200. Unsupported extensions, empty files, malformed CSV,
and invalid UTF-8 return 400. Missing configured columns and unsupported enabled
processing settings also return 400. Missing datasets return 404. Invalid parameters
such as `limit=0`, or an invalid processing request body, return 422. Extensions are
case insensitive.

## Demonstrate Part 1 in `/docs`

1. Expand `GET /health`, select **Try it out**, and select **Execute**.
2. Expand `POST /upload`, select **Try it out**, choose
   `fixtures/sample_data.csv`, and select **Execute**. Expect six rows and two columns:

   ```json
   {
     "id": 1,
     "filename": "sample_data.csv",
     "rows": 6,
     "columns": 2,
     "column_names": ["student_id", "score"]
   }
   ```

3. Expand `GET /datasets/{dataset_id}`, select **Try it out**, enter the returned
   ID and `limit=2`, then select **Execute**:

   ```json
   {
     "id": 1,
     "data": [
       {"student_id": 1, "score": "80"},
       {"student_id": 2, "score": "90"}
     ],
     "total_rows": 6
   }
   ```

4. Retrieve an unused ID such as `999`; expect 404.
5. Upload `README.md`; expect 400 for its unsupported extension.
6. Retrieve the uploaded ID with `limit=0`; expect 422.

IDs increase with each successful upload. Duplicate rows and the text `unknown`
remain in the dataset. Because `score` mixes numbers with text, its values are
strings. The missing score in the fourth row is returned as JSON `null` when
retrieving at least four rows. Limiting a response leaves all six stored rows intact.

## Demonstrate Part 2: upload, process, retrieve

Upload a fresh `fixtures/sample_data.csv` and note the returned ID. In `/docs`,
expand `POST /datasets/{dataset_id}/process`, select **Try it out**, enter that ID,
and replace the request body with:

```json
{
  "validation": {
    "required_columns": ["student_id", "score"],
    "numeric_columns": ["score"]
  },
  "processing": {
    "remove_duplicates": true,
    "missing": {"enabled": true, "axis": "rows"},
    "outliers": {
      "enabled": false,
      "columns": [],
      "method": "iqr",
      "threshold": 1.5
    }
  }
}
```

Select **Execute**. On a fresh upload with ID 1, expect:

```json
{
  "id": 1,
  "validation_rows_removed": 1,
  "cleaning_report": {
    "rows_before": 5,
    "rows_after": 3,
    "rows_removed": 2,
    "columns_before": 2,
    "columns_after": 2,
    "columns_removed": 0
  }
}
```

Numeric validation removes the row containing `unknown`: **6 → 5 rows**.
Duplicate removal then produces **5 → 4 rows**, and missing-value removal produces
**4 → 3 rows**. The cleaning report begins after validation, so it reports two
cleaning removals separately from the one validation removal.

Retrieve the same ID with `GET /datasets/{dataset_id}`. The response has
`total_rows: 3` and records for student IDs 1, 2, and 5 with numeric scores
80, 90, and 85. Processing replaces that dataset; upload a fresh copy when repeating
a test that requires the original six rows. A failed validation or processing
request leaves the uploaded data and metadata unchanged.

An empty configuration `{}` uses fresh nested defaults: no required or numeric
columns, duplicate removal enabled, missing rows removed, and outlier removal
disabled. Specify `numeric_columns: ["score"]` to remove the sample's `unknown`
value during validation. Missing-value handling accepts `rows` or `columns`;
enabled outlier handling accepts `iqr` or `zscore` and a nonnegative threshold.
Unsupported axis and method strings are handled by the copied MP1 functions.

## Request logs and response IDs

Every response includes a new eight-character `X-Request-ID`, including error
responses. The matching log entry contains the HTTP method, path, status code,
and duration in milliseconds, for example:

```text
10:15:02 INFO     main — Processed dataset: id=1, validation_removed=1, rows_before=5, rows_after=3
10:15:02 INFO     src.middleware — request_id=a3f2c1d8 POST /datasets/1/process status=200 duration=12.4ms
```

The middleware logs successful responses at INFO, 4xx responses at WARNING, and
5xx responses at ERROR. Unexpected exceptions include a traceback in the server
log and return status 500 with `{"detail": "Internal server error"}` to the client.

## How the modules work

| File | Responsibility |
| --- | --- |
| `main.py` | Handle uploads, retrieval, and the validate → process → report → update workflow. |
| `src/models.py` | Define health/dataset responses, nested processing settings, and the processing report. |
| `src/storage.py` | Assign IDs, store DataFrame copies and filenames, and provide get/update/clear operations. |
| `src/utils.py` | Configure logging using the function copied from MP1. |
| `src/middleware.py` | Add response request IDs, log request timing and severity, and handle unexpected exceptions. |
| `src/__init__.py` | Export the models, storage class, middleware, and logging function. |
| `data_pipeline/` | Contain all six reusable MP1 Python modules, including their package exports. |
| `fixtures/sample_data.csv` | Supply the assignment's six-row example. |
| `tests/conftest.py` | Provide the shared client, CSV bytes, upload ID, and processing-body fixtures. |
| `tests/` | Check the full API workflow, failure isolation, request logs, model defaults, and storage copies. |

`save()` and `update()` copy their inputs. `get()` returns a copy, so callers must
use `update()` to replace stored data. Metadata is calculated from the current
DataFrame each time, preserving the original filename after updates.
`clear()` empties storage and resets the next ID to 1.

Storage lives in one server process. Restarting the server, including an automatic
reload after an edit, removes uploaded datasets. Use the single-process run command
above so uploads and retrievals share the same storage instance.

## Tests

```powershell
python -m pytest tests -v
```

All **66 tests** pass. The three required Part 2 API tests are `test_upload_csv`,
`test_process_and_retrieve`, and `test_retrieve_missing_dataset`. Additional tests
cover Part 1 behavior, failed processing without data changes, default and disabled
settings, IQR/Z-score outliers, updated metadata, repeated processing, request IDs,
log levels, duration, and unexpected exceptions. Each API test starts with empty
storage. The installed Starlette TestClient emits one httpx deprecation warning.

`requirements.txt` records the installed versions using `python -m pip freeze`.
The sample data and tests are committed. Environments, caches, local configuration,
and generated files are excluded by `.gitignore`.

## Short explanation for check-off

"I connected the reusable MP1 modules to the API's processing endpoint. The sample
goes from six uploaded rows to five after numeric validation and three after
duplicate and missing-value removal. Storage is updated only after processing
succeeds. The middleware logs request IDs, status codes, and durations, and the
test suite checks both successful workflows and errors."
