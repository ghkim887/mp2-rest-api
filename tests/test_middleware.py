"""Verify request correlation, severity, timing, and unexpected-error handling."""

import logging
import re

import pandas as pd
import pytest

import main


@pytest.mark.parametrize("status", [200, 400, 404, 422])
def test_request_id_timing_and_log_level(client, caplog, status):
    with caplog.at_level(logging.INFO, logger="src.middleware"):
        if status == 200:
            response = client.get("/health")
        elif status == 400:
            response = client.post("/upload", files={"file": ("bad.txt", b"bad", "text/plain")})
        elif status == 404:
            response = client.get("/datasets/999")
        else:
            response = client.get("/datasets/999", params={"limit": 0})

    assert response.status_code == status
    request_id = response.headers["X-Request-ID"]
    assert re.fullmatch(r"[0-9a-f]{8}", request_id)
    records = [record for record in caplog.records if record.name == "src.middleware"]
    assert len(records) == 1
    assert records[0].levelno == (logging.INFO if status == 200 else logging.WARNING)
    message = records[0].getMessage()
    assert f"request_id={request_id} {response.request.method} {response.request.url.path}" in message
    assert f"status={status}" in message
    duration = re.search(r"duration=(\d+\.\d+)ms", message)
    assert duration is not None
    assert float(duration.group(1)) >= 0


def test_requests_have_different_ids(client):
    first = client.get("/health").headers["X-Request-ID"]
    second = client.get("/health").headers["X-Request-ID"]
    assert first != second


def test_processing_response_has_request_id(client, uploaded_dataset_id, processing_body):
    response = client.post(f"/datasets/{uploaded_dataset_id}/process", json=processing_body)
    assert response.status_code == 200
    assert re.fullmatch(r"[0-9a-f]{8}", response.headers["X-Request-ID"])


def test_unexpected_processing_error_is_logged_and_returns_generic_500(
    client, uploaded_dataset_id, processing_body, monkeypatch, caplog
):
    before = main.storage.get(uploaded_dataset_id)

    def fail_processing(df, config):
        raise RuntimeError("private failure detail")

    monkeypatch.setattr(main, "process_data", fail_processing)
    with caplog.at_level(logging.ERROR, logger="src.middleware"):
        response = client.post(
            f"/datasets/{uploaded_dataset_id}/process", json=processing_body
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "private failure detail" not in response.text
    request_id = response.headers["X-Request-ID"]
    assert re.fullmatch(r"[0-9a-f]{8}", request_id)
    records = [record for record in caplog.records if record.name == "src.middleware"]
    assert len(records) == 2
    assert all(record.levelno == logging.ERROR for record in records)
    assert all(f"request_id={request_id}" in record.getMessage() for record in records)
    assert records[0].exc_info is not None
    assert "RuntimeError: private failure detail" in caplog.text
    assert "status=500" in records[1].getMessage()
    pd.testing.assert_frame_equal(main.storage.get(uploaded_dataset_id), before)
