"""Check processing defaults and independent nested settings."""

from src import ProcessConfig


def test_processing_defaults_match_mp1_configuration():
    assert ProcessConfig().model_dump() == {
        "validation": {"required_columns": [], "numeric_columns": []},
        "processing": {
            "remove_duplicates": True,
            "missing": {"enabled": True, "axis": "rows"},
            "outliers": {"enabled": False, "columns": [], "method": "iqr", "threshold": 1.5},
        },
    }


def test_default_lists_and_nested_models_are_independent():
    first, second = ProcessConfig(), ProcessConfig()
    first.validation.required_columns.append("student_id")
    first.validation.numeric_columns.append("score")
    first.processing.outliers.columns.append("score")
    first.processing.missing.axis = "columns"
    assert second.validation.required_columns == []
    assert second.validation.numeric_columns == []
    assert second.processing.outliers.columns == []
    assert second.processing.missing.axis == "rows"
