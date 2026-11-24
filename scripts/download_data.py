"""Download the official UCI Bike Sharing Dataset (day.csv, CC BY 4.0)."""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils import sha256_file

UCI_DATASET_URL = (
    "https://archive.ics.uci.edu/static/public/275/bike+sharing+dataset.zip"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "raw" / "day.csv"


def download_bike_dataset(output_path: Path = DEFAULT_OUTPUT, force: bool = False) -> Path:
    """Download UCI Bike Sharing Dataset ZIP and extract day.csv."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not force:
        print(
            f"[download_data] Dataset already exists: {output_path} "
            f"(sha256={sha256_file(output_path)[:16]}...)"
        )
        return output_path

    print(f"[download_data] Downloading UCI Bike Sharing Dataset from {UCI_DATASET_URL} ...")
    response = requests.get(UCI_DATASET_URL, timeout=60)
    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        if "day.csv" not in zf.namelist():
            raise FileNotFoundError("day.csv was not found inside the UCI archive.")
        with zf.open("day.csv") as src, output_path.open("wb") as dst:
            dst.write(src.read())

    digest = sha256_file(output_path)
    print(f"[download_data] Extracted day.csv -> {output_path} (sha256={digest})")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download UCI Bike Sharing day.csv")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true", help="Re-download even if file exists")
    args = parser.parse_args()
    download_bike_dataset(output_path=args.output, force=args.force)


if __name__ == "__main__":
    main()
