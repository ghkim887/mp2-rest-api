"""Write cleaned data to a CSV file."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def save_data(df, filepath):
    """Save a DataFrame as CSV without an index and return its Path."""
    path = Path(filepath)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
    except OSError as error:
        logger.error(f"Unable to save CSV to {path}: {error}")
        raise
    logger.debug(f"Saved {len(df)} rows to {path}")
    return path
