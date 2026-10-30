"""Reusable, configuration-driven DataFrame cleaning functions."""

import logging
import math

import pandas as pd

logger = logging.getLogger(__name__)


def _config_error(message):
    """Report invalid processing settings to the calling program."""
    logger.error(message)
    raise ValueError(message)


def _step_settings(processing, name, required):
    """Validate a processing section before its settings are used."""
    settings = processing.get(name, {})
    if not isinstance(settings, dict):
        _config_error(f"processing.{name} must be a mapping")
    if not isinstance(settings.get("enabled", False), bool):
        _config_error(f"processing.{name}.enabled must be true or false")
    if settings.get("enabled", False):
        for key in required:
            if key not in settings:
                _config_error(f"Missing required setting: processing.{name}.{key}")
    return settings


def remove_duplicates(df):
    """Remove duplicate rows."""
    result = df.drop_duplicates()
    logger.debug(f"remove_duplicates: {len(df)} → {len(result)} rows; removed={len(df) - len(result)}")
    return result


def handle_missing(df, axis="rows"):
    """Drop rows or columns containing missing values."""
    if axis not in ("rows", "columns"):
        logger.error(f"Unsupported missing-value axis: {axis}")
        raise ValueError(f"Unsupported missing-value axis: {axis}")
    result = df.dropna(axis=0 if axis == "rows" else 1)
    before = df.shape[0 if axis == "rows" else 1]
    after = result.shape[0 if axis == "rows" else 1]
    logger.debug(f"handle_missing: {before} → {after} {axis}; removed={before - after}")
    return result


def remove_outliers(df, columns, method, threshold):
    """Remove outliers sequentially from the specified numeric columns."""
    if method not in ("iqr", "zscore"):
        logger.error(f"Unsupported outlier method: {method}")
        raise ValueError(f"Unsupported outlier method: {method}")
    if not isinstance(columns, list) or not all(isinstance(column, str) for column in columns):
        _config_error("Outlier columns must be a list of column names")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or threshold < 0:
        logger.error(f"Invalid outlier threshold: {threshold}")
        raise ValueError(f"Invalid outlier threshold: {threshold}")
    result = df
    for column in columns:
        if column not in result.columns:
            logger.warning(f"Column not found: {column}")
            continue
        if not pd.api.types.is_numeric_dtype(result[column]):
            logger.warning(f"Column is not numeric: {column}")
            continue
        values = result[column]
        if method == "iqr":
            q1, q3 = values.quantile([0.25, 0.75])
            iqr = q3 - q1
            lower, upper = q1 - threshold * iqr, q3 + threshold * iqr
            outliers = (values < lower) | (values > upper)
        else:
            # Population standard deviation; constant columns have no outliers.
            std = values.std(ddof=0)
            if pd.isna(std) or std == 0:
                outliers = pd.Series(False, index=result.index)
            else:
                outliers = ((values - values.mean()) / std).abs() > threshold
        # Missing values are handled by their own configurable step.
        outliers = outliers.fillna(False)
        before = len(result)
        result = result.loc[~outliers]
        logger.debug(
            f"{column}: method={method}, threshold={threshold}, removed={before - len(result)}"
        )
    return result


def process_data(df, config):
    """Apply enabled steps in the order duplicates, missing values, outliers."""
    if not isinstance(df, pd.DataFrame):
        logger.error("Processing requires tabular CSV data")
        raise ValueError("Processing requires tabular CSV data")
    if not isinstance(config, dict) or not isinstance(config.get("processing"), dict):
        logger.error("Configuration must contain a processing mapping")
        raise ValueError("Configuration must contain a processing mapping")
    processing = config["processing"]
    if not isinstance(processing.get("remove_duplicates", False), bool):
        _config_error("processing.remove_duplicates must be true or false")
    missing = _step_settings(processing, "missing", ["axis"])
    outliers = _step_settings(processing, "outliers", ["columns", "method", "threshold"])
    result = df
    if processing.get("remove_duplicates", False):
        result = remove_duplicates(result)
    if missing.get("enabled", False):
        result = handle_missing(result, axis=missing["axis"])
    if outliers.get("enabled", False):
        result = remove_outliers(
            result, columns=outliers["columns"],
            method=outliers["method"], threshold=outliers["threshold"],
        )
    return result


def create_cleaning_report(df_before, df_after):
    """Return a dictionary summarizing the cleaning results."""
    return {
        "rows_before": len(df_before),
        "rows_after": len(df_after),
        "rows_removed": len(df_before) - len(df_after),
        "columns_before": len(df_before.columns),
        "columns_after": len(df_after.columns),
        "columns_removed": len(df_before.columns) - len(df_after.columns),
    }
