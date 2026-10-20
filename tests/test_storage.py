"""Verify dataset ownership, metadata, and storage lifecycle."""

import logging

import pandas as pd
import pytest

from src import DatasetStorage


@pytest.fixture
def storage():
    return DatasetStorage()


@pytest.fixture
def dataframe():
    return pd.DataFrame({"student_id": [1, 2], "score": [80, 90]})


def test_save_assigns_sequential_ids_and_keeps_datasets_separate(storage, dataframe):
    first_id = storage.save(dataframe, "first.csv")
    second_id = storage.save(dataframe.head(1), "second.csv")
    assert (first_id, second_id) == (1, 2)
    assert storage.get_metadata(first_id) == {
        "id": 1,
        "filename": "first.csv",
        "rows": 2,
        "columns": 2,
        "column_names": ["student_id", "score"],
    }
    assert storage.get_metadata(second_id)["filename"] == "second.csv"
    assert len(storage.get(first_id)) == 2
    assert len(storage.get(second_id)) == 1


def test_save_owns_a_copy_of_the_input(storage, dataframe):
    dataset_id = storage.save(dataframe, "sample.csv")
    dataframe.loc[0, "score"] = 0
    assert storage.get(dataset_id).loc[0, "score"] == 80


def test_get_returns_an_independent_copy(storage, dataframe):
    dataset_id = storage.save(dataframe, "sample.csv")
    retrieved = storage.get(dataset_id)
    retrieved.loc[0, "score"] = 0
    retrieved.drop(columns=["student_id"], inplace=True)
    pd.testing.assert_frame_equal(storage.get(dataset_id), dataframe)


def test_update_refreshes_metadata_and_preserves_filename(storage, dataframe):
    dataset_id = storage.save(dataframe, "sample.csv")
    replacement = pd.DataFrame({"student_id": [3], "passed": [True], "rank": [1]})
    assert storage.update(dataset_id, replacement) is True
    pd.testing.assert_frame_equal(storage.get(dataset_id), replacement)
    assert storage.get_metadata(dataset_id) == {
        "id": dataset_id,
        "filename": "sample.csv",
        "rows": 1,
        "columns": 3,
        "column_names": ["student_id", "passed", "rank"],
    }


def test_update_owns_a_copy_of_the_replacement(storage, dataframe):
    dataset_id = storage.save(dataframe, "sample.csv")
    replacement = pd.DataFrame({"score": [100]})
    storage.update(dataset_id, replacement)
    replacement.loc[0, "score"] = 0
    assert storage.get(dataset_id).loc[0, "score"] == 100


def test_metadata_cannot_be_used_to_mutate_storage(storage, dataframe):
    dataset_id = storage.save(dataframe, "sample.csv")
    metadata = storage.get_metadata(dataset_id)
    metadata["column_names"].append("extra")
    metadata["filename"] = "changed.csv"
    assert storage.get_metadata(dataset_id)["column_names"] == ["student_id", "score"]
    assert storage.get_metadata(dataset_id)["filename"] == "sample.csv"


@pytest.mark.parametrize("dataset_id", [1, 999, -1])
def test_missing_datasets_are_not_created_by_lookup_or_update(storage, dataframe, dataset_id):
    assert storage.get(dataset_id) is None
    assert storage.get_metadata(dataset_id) is None
    assert storage.update(dataset_id, dataframe) is False
    assert storage.get(dataset_id) is None
    assert storage.save(dataframe, "first.csv") == 1


def test_clear_removes_data_and_resets_ids(storage, dataframe):
    first_id = storage.save(dataframe, "first.csv")
    second_id = storage.save(dataframe, "second.csv")
    storage.clear()
    assert storage.get(first_id) is None
    assert storage.get_metadata(second_id) is None
    assert storage.save(dataframe, "new.csv") == 1


def test_storage_operations_log_at_debug(storage, dataframe, caplog):
    with caplog.at_level(logging.DEBUG, logger="src.storage"):
        dataset_id = storage.save(dataframe, "sample.csv")
        storage.get(dataset_id)
        storage.get_metadata(dataset_id)
        storage.update(dataset_id, dataframe.head(1))
        storage.clear()
    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == 5
    assert all(record.levelno == logging.DEBUG for record in caplog.records)
    assert "Stored dataset: id=1, rows=2" in messages
    assert "Updated dataset: id=1, rows=1" in messages
