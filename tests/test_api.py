"""Exercise HTTP contracts using the supplied course fixture."""

import logging
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import main

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "sample_data.csv"


@pytest.fixture
def client():
    main.storage.clear()
    with TestClient(main.app) as test_client:
        yield test_client
    main.storage.clear()


def upload_sample(client, filename="sample_data.csv"):
    return client.post(
        "/upload",
        files={"file": (filename, SAMPLE_PATH.read_bytes(), "text/csv")},
    )


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.0"}


def test_upload_returns_course_fixture_metadata(client):
    response = upload_sample(client)
    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "filename": "sample_data.csv",
        "rows": 6,
        "columns": 2,
        "column_names": ["student_id", "score"],
    }


def test_upload_accepts_uppercase_csv_extension(client):
    response = upload_sample(client, "SAMPLE.CSV")
    assert response.status_code == 200
    assert response.json()["filename"] == "SAMPLE.CSV"


def test_retrieval_limits_rows_without_modifying_storage(client):
    dataset_id = upload_sample(client).json()["id"]
    before = main.storage.get(dataset_id)
    response = client.get(f"/datasets/{dataset_id}", params={"limit": 2})
    assert response.status_code == 200
    assert response.json() == {
        "id": dataset_id,
        "data": [{"student_id": 1, "score": "80"}, {"student_id": 2, "score": "90"}],
        "total_rows": 6,
    }
    pd.testing.assert_frame_equal(main.storage.get(dataset_id), before)


def test_retrieval_keeps_duplicates_order_and_null_values(client):
    dataset_id = upload_sample(client).json()["id"]
    response = client.get(f"/datasets/{dataset_id}")
    assert response.status_code == 200
    assert response.json() == {
        "id": dataset_id,
        "data": [
            {"student_id": 1, "score": "80"},
            {"student_id": 2, "score": "90"},
            {"student_id": 2, "score": "90"},
            {"student_id": 3, "score": None},
            {"student_id": 4, "score": "unknown"},
            {"student_id": 5, "score": "85"},
        ],
        "total_rows": 6,
    }
    assert "NaN" not in response.text


def test_default_limit_is_100_and_total_rows_is_full_size(client):
    contents = "value\n" + "\n".join(str(value) for value in range(125))
    dataset_id = client.post(
        "/upload", files={"file": ("large.csv", contents, "text/csv")}
    ).json()["id"]
    body = client.get(f"/datasets/{dataset_id}").json()
    assert len(body["data"]) == 100
    assert body["data"][0] == {"value": 0}
    assert body["data"][-1] == {"value": 99}
    assert body["total_rows"] == 125


def test_multiple_uploads_use_separate_ids(client):
    assert upload_sample(client).json()["id"] == 1
    assert upload_sample(client).json()["id"] == 2
    assert client.get("/datasets/1").json()["total_rows"] == 6
    assert client.get("/datasets/2").json()["total_rows"] == 6


def test_missing_dataset_returns_404_and_warning(client, caplog):
    with caplog.at_level(logging.WARNING, logger="main"):
        response = client.get("/datasets/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Dataset 999 not found."}
    assert "Dataset not found: 999" in caplog.text


@pytest.mark.parametrize("filename", ["sample.txt", "sample.json", "sample", "sample.csv.exe"])
def test_unsupported_upload_returns_400_without_using_an_id(client, filename, caplog):
    with caplog.at_level(logging.WARNING, logger="main"):
        response = upload_sample(client, filename)
    assert response.status_code == 400
    assert response.json() == {"detail": "Only .csv files are supported."}
    assert "Unsupported file format" in caplog.text
    assert upload_sample(client).json()["id"] == 1


@pytest.mark.parametrize(
    "contents",
    [b"", b"\n\n", b'student_id,score\n1,"unterminated\n', b"student_id,score\n1,\xff\n"],
    ids=["empty", "blank", "malformed", "invalid-utf8"],
)
def test_unreadable_csv_returns_400_without_storing_data(client, contents, caplog):
    with caplog.at_level(logging.WARNING, logger="main"):
        response = client.post(
            "/upload", files={"file": ("invalid.csv", contents, "text/csv")}
        )
    assert response.status_code == 400
    assert "Unable to read CSV" in response.json()["detail"]
    assert "Unable to read CSV upload" in caplog.text
    assert main.storage.get(1) is None
    assert upload_sample(client).json()["id"] == 1


@pytest.mark.parametrize("limit", [0, -1, "abc", "1.5"])
def test_invalid_limits_return_422(client, limit):
    dataset_id = upload_sample(client).json()["id"]
    assert client.get(f"/datasets/{dataset_id}", params={"limit": limit}).status_code == 422


def test_invalid_dataset_id_returns_422(client):
    assert client.get("/datasets/abc").status_code == 422


def test_missing_file_returns_422(client):
    assert client.post("/upload").status_code == 422


def test_header_only_csv_is_a_valid_empty_dataset(client):
    uploaded = client.post(
        "/upload", files={"file": ("headers.csv", b"student_id,score\n", "text/csv")}
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["rows"] == 0
    assert uploaded.json()["columns"] == 2
    dataset_id = uploaded.json()["id"]
    assert client.get(f"/datasets/{dataset_id}").json() == {
        "id": dataset_id, "data": [], "total_rows": 0
    }


def test_upload_and_retrieval_log_ids_and_row_counts(client, caplog):
    with caplog.at_level(logging.INFO, logger="main"):
        upload_sample(client)
        client.get("/datasets/1", params={"limit": 2})
    assert "Uploaded dataset: id=1, filename=sample_data.csv, rows=6" in caplog.text
    assert "Retrieved dataset: id=1, returned_rows=2" in caplog.text


def test_docs_expose_response_models_and_endpoints(client):
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/health"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/HealthResponse")
    assert schema["paths"]["/upload"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/DatasetInfo")
    assert "/datasets/{dataset_id}" in schema["paths"]
