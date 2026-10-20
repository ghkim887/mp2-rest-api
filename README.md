# MP2 REST API — Part 1

A FastAPI application for uploading CSV files, storing pandas DataFrames in memory,
and retrieving rows through HTTP. The project reuses MP1's `setup_logging()` with
the same INFO/DEBUG behavior and timestamp, level, logger name, and message format.

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

Successful requests return 200. Unsupported extensions, empty files, malformed CSV,
and invalid UTF-8 return 400. Missing datasets return 404. Invalid parameters such
as `limit=0` return 422. Extensions are case insensitive.

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

## How the modules work

| File | Responsibility |
| --- | --- |
| `main.py` | Configure the application, handle requests, parse CSV, and log uploads and retrievals. |
| `src/models.py` | Define the `HealthResponse` and `DatasetInfo` response models. |
| `src/storage.py` | Assign IDs, store DataFrame copies and filenames, and provide get/update/clear operations. |
| `src/utils.py` | Configure logging using the function copied from MP1. |
| `src/__init__.py` | Export the models, storage class, and logging function. |
| `fixtures/sample_data.csv` | Supply the assignment's six-row example. |
| `tests/` | Check endpoint contracts, error paths, logs, copy isolation, and metadata updates. |

`save()` and `update()` copy their inputs. `get()` returns a copy, so callers must
use `update()` to replace stored data. Metadata is calculated from the current
DataFrame each time, preserving the original filename after updates.
`clear()` empties storage and resets the next ID to 1.

Storage lives in one server process. Restarting the server, including an automatic
reload after an edit, removes uploaded datasets. Use the single-process run command
above so uploads and retrievals share the same storage instance.

## Tests

```powershell
python -m pytest -q
```

The test client exercises the actual sample file and checks row limits, row order,
duplicates, JSON nulls, multiple IDs, invalid uploads, parameter validation, logs,
and generated API documentation. Storage tests verify that modifying inputs or
returned objects cannot silently change stored data and that updates refresh
metadata. Each API test starts with empty storage.

`requirements.txt` records the installed versions using `python -m pip freeze`.
The sample data and tests are committed. Environments, caches, local configuration,
and generated files are excluded by `.gitignore`.

## Short explanation for check-off

"I reused the logging setup from MP1 and built three FastAPI endpoints. Uploads
are parsed with pandas and stored as copies with sequential IDs. Retrieval returns
the requested number of rows while reporting the full dataset size, and invalid
files or parameters receive the appropriate HTTP status codes."
