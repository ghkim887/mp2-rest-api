"""Validate required columns and configured numeric values."""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def validate_dataframe(df, required_columns, numeric_columns):
    """Return a validated DataFrame without changing the caller's data."""
    if not isinstance(df, pd.DataFrame):
        logger.error("Validation requires tabular CSV data")
        raise ValueError("Validation requires tabular CSV data")
    for column in required_columns:
        if column not in df.columns:
            logger.error(f"Required column missing: {column}")
            raise ValueError(f"Required column missing: {column}")
    result = df.copy()
    before = len(result)
    for column in numeric_columns:
        if column not in result.columns:
            logger.error(f"Numeric column missing: {column}")
            raise ValueError(f"Numeric column missing: {column}")
        invalid_rows = []
        for index, value in result[column].items():
            if pd.notna(value):
                try:
                    float(value)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid numeric value in {column} at row index {index}")
                    invalid_rows.append(index)
        result = result.drop(index=invalid_rows)
        result[column] = pd.to_numeric(result[column])
    logger.debug(f"Validation: {before} → {len(result)} rows; removed={before - len(result)}")
    return result
