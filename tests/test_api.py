"""Exercise HTTP contracts using the supplied course fixture."""

import logging
from pathlib import Path

import pandas as pd
import pytest

import main

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "sample_data.csv"


def upload_sample(client, filename="sample_data.csv"):
    return client.post(
        "/upload",
        files={"file": (filename, SAMPLE_PATH.read_bytes(), "text/csv")},
    )


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.0"}


def test_upload_csv(client, sample_csv_bytes):
    response = client.post(
        "/upload", files={"file": ("sample_data.csv", sample_csv_bytes, "text/csv")}
    )
    assert response.status_code == 200
    assert isinstance(response.json()["id"], int)
    assert response.json()["id"] > 0
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


def test_retrieve_missing_dataset(client, caplog):
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
    process = schema["paths"]["/datasets/{dataset_id}/process"]["post"]
    assert process["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ProcessConfig"
    )
    assert process["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/ProcessingReport")


def test_process_and_retrieve(client, uploaded_dataset_id, processing_body):
    response = client.post(
        f"/datasets/{uploaded_dataset_id}/process", json=processing_body
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": uploaded_dataset_id,
        "validation_rows_removed": 1,
        "cleaning_report": {
            "rows_before": 5,
            "rows_after": 3,
            "rows_removed": 2,
            "columns_before": 2,
            "columns_after": 2,
            "columns_removed": 0,
        },
    }

    retrieved = client.get(f"/datasets/{uploaded_dataset_id}")
    assert retrieved.status_code == 200
    assert retrieved.json() == {
        "id": uploaded_dataset_id,
        "data": [
            {"student_id": 1, "score": 80},
            {"student_id": 2, "score": 90},
            {"student_id": 5, "score": 85},
        ],
        "total_rows": 3,
    }
    assert main.storage.get_metadata(uploaded_dataset_id) == {
        "id": uploaded_dataset_id,
        "filename": "sample_data.csv",
        "rows": 3,
        "columns": 2,
        "column_names": ["student_id", "score"],
    }


def test_process_missing_dataset_returns_404(client, processing_body):
    response = client.post("/datasets/999/process", json=processing_body)
    assert response.status_code == 404
    assert response.json() == {"detail": "Dataset 999 not found."}


@pytest.mark.parametrize(
    "section,changes,detail",
    [
        ("validation", {"required_columns": ["missing"]}, "Required column missing: missing"),
        ("validation", {"numeric_columns": ["missing"]}, "Numeric column missing: missing"),
        ("missing", {"axis": "invalid"}, "Unsupported missing-value axis: invalid"),
        (
            "outliers",
            {"enabled": True, "columns": ["score"], "method": "invalid"},
            "Unsupported outlier method: invalid",
        ),
        (
            "outliers",
            {"enabled": True, "columns": ["score"], "threshold": -1},
            "Invalid outlier threshold: -1.0",
        ),
    ],
)
def test_failed_processing_preserves_original_data(
    client, uploaded_dataset_id, processing_body, section, changes, detail
):
    if section == "validation":
        processing_body[section].update(changes)
    else:
        processing_body["processing"][section].update(changes)
    before = main.storage.get(uploaded_dataset_id)
    metadata_before = main.storage.get_metadata(uploaded_dataset_id)

    response = client.post(
        f"/datasets/{uploaded_dataset_id}/process", json=processing_body
    )
    assert response.status_code == 400
    assert response.json() == {"detail": detail}
    pd.testing.assert_frame_equal(main.storage.get(uploaded_dataset_id), before)
    assert main.storage.get_metadata(uploaded_dataset_id) == metadata_before
    retrieved = client.get(f"/datasets/{uploaded_dataset_id}").json()
    assert retrieved["total_rows"] == 6
    assert retrieved["data"][4]["score"] == "unknown"


@pytest.mark.parametrize(
    "body",
    [None, [], {"validation": None}, {"processing": {"missing": {"axis": 1}}}],
    ids=["no-config", "array-config", "null-validation", "invalid-field-type"],
)
def test_malformed_processing_body_returns_422_without_changes(client, uploaded_dataset_id, body):
    before = main.storage.get(uploaded_dataset_id)
    response = client.post(f"/datasets/{uploaded_dataset_id}/process", json=body)
    assert response.status_code == 422
    pd.testing.assert_frame_equal(main.storage.get(uploaded_dataset_id), before)


def test_processing_uses_nested_defaults(client, uploaded_dataset_id):
    response = client.post(
        f"/datasets/{uploaded_dataset_id}/process",
        json={"validation": {"numeric_columns": ["score"]}},
    )
    assert response.status_code == 200
    assert response.json()["validation_rows_removed"] == 1
    assert response.json()["cleaning_report"]["rows_after"] == 3


def test_empty_config_cleans_without_numeric_validation(client, uploaded_dataset_id):
    response = client.post(f"/datasets/{uploaded_dataset_id}/process", json={})
    assert response.status_code == 200
    assert response.json()["validation_rows_removed"] == 0
    assert response.json()["cleaning_report"]["rows_before"] == 6
    assert response.json()["cleaning_report"]["rows_after"] == 4
    rows = client.get(f"/datasets/{uploaded_dataset_id}").json()["data"]
    assert [row["student_id"] for row in rows] == [1, 2, 4, 5]
    assert rows[2]["score"] == "unknown"


def test_disabled_processing_steps_preserve_duplicates_and_nulls(
    client, uploaded_dataset_id, processing_body
):
    processing_body["processing"]["remove_duplicates"] = False
    processing_body["processing"]["missing"]["enabled"] = False
    response = client.post(
        f"/datasets/{uploaded_dataset_id}/process", json=processing_body
    )
    assert response.status_code == 200
    assert response.json()["validation_rows_removed"] == 1
    assert response.json()["cleaning_report"]["rows_removed"] == 0
    rows = client.get(f"/datasets/{uploaded_dataset_id}").json()["data"]
    assert [row["student_id"] for row in rows] == [1, 2, 2, 3, 5]
    assert rows[3]["score"] is None


def test_missing_column_removal_refreshes_storage_metadata(
    client, uploaded_dataset_id, processing_body
):
    processing_body["processing"]["missing"]["axis"] = "columns"
    response = client.post(
        f"/datasets/{uploaded_dataset_id}/process", json=processing_body
    )
    assert response.status_code == 200
    assert response.json()["cleaning_report"] == {
        "rows_before": 5, "rows_after": 4, "rows_removed": 1,
        "columns_before": 2, "columns_after": 1, "columns_removed": 1,
    }
    assert main.storage.get_metadata(uploaded_dataset_id)["column_names"] == ["student_id"]
    assert client.get(f"/datasets/{uploaded_dataset_id}").json()["data"] == [
        {"student_id": student_id} for student_id in [1, 2, 3, 5]
    ]


@pytest.mark.parametrize("method", ["iqr", "zscore"])
def test_outlier_methods_reuse_mp1_behavior(client, processing_body, method):
    uploaded = client.post(
        "/upload", files={"file": ("outliers.csv", b"value\n10\n11\n12\n13\n100\n", "text/csv")}
    )
    assert uploaded.status_code == 200
    dataset_id = uploaded.json()["id"]
    processing_body["validation"] = {"required_columns": ["value"], "numeric_columns": ["value"]}
    processing_body["processing"]["outliers"].update(
        {"enabled": True, "columns": ["value"], "method": method}
    )
    response = client.post(f"/datasets/{dataset_id}/process", json=processing_body)
    assert response.status_code == 200
    assert response.json()["cleaning_report"]["rows_removed"] == 1
    assert client.get(f"/datasets/{dataset_id}").json()["data"] == [
        {"value": value} for value in [10, 11, 12, 13]
    ]


def test_disabled_steps_ignore_unsupported_axis_and_method(
    client, uploaded_dataset_id, processing_body
):
    processing_body["processing"]["missing"] = {"enabled": False, "axis": "invalid"}
    processing_body["processing"]["outliers"]["method"] = "invalid"
    response = client.post(
        f"/datasets/{uploaded_dataset_id}/process", json=processing_body
    )
    assert response.status_code == 200
    assert response.json()["cleaning_report"]["rows_after"] == 4


def test_processing_leaves_other_uploads_unchanged(client, uploaded_dataset_id, processing_body):
    second_id = upload_sample(client).json()["id"]
    before = main.storage.get(second_id)
    assert client.post(
        f"/datasets/{uploaded_dataset_id}/process", json=processing_body
    ).status_code == 200
    pd.testing.assert_frame_equal(main.storage.get(second_id), before)
    assert client.get(f"/datasets/{second_id}").json()["total_rows"] == 6


def test_repeated_processing_reports_current_data(client, uploaded_dataset_id, processing_body):
    endpoint = f"/datasets/{uploaded_dataset_id}/process"
    assert client.post(endpoint, json=processing_body).status_code == 200
    repeated = client.post(endpoint, json=processing_body)
    assert repeated.status_code == 200
    assert repeated.json() == {
        "id": uploaded_dataset_id,
        "validation_rows_removed": 0,
        "cleaning_report": {
            "rows_before": 3, "rows_after": 3, "rows_removed": 0,
            "columns_before": 2, "columns_after": 2, "columns_removed": 0,
        },
    }


def test_processing_logs_major_results(client, uploaded_dataset_id, processing_body, caplog):
    with caplog.at_level(logging.INFO, logger="main"):
        response = client.post(
            f"/datasets/{uploaded_dataset_id}/process", json=processing_body
        )
    assert response.status_code == 200
    assert f"Validated dataset: id={uploaded_dataset_id}, rows_before=6, rows_after=5" in caplog.text
    assert (
        f"Processed dataset: id={uploaded_dataset_id}, validation_removed=1, rows_before=5, rows_after=3"
        in caplog.text
    )
