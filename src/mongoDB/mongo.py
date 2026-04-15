import pandas as pd
from pymongo import MongoClient
from pymongo.database import Database
from pathlib import Path

BASE_DIR      = Path(__file__).parent.parent  # src/
PROCESSED_DIR = BASE_DIR / 'csv' / 'processed'

CONNECTION_STRING = "mongodb://localhost:27017"
DATABASE_NAME     = "groundtruth"


def _import_csv(db: Database, csv_file: Path) -> None:
    collection_name = csv_file.stem
    print(f"  {csv_file.name} -> {collection_name}", end=" ... ")

    df = pd.read_csv(csv_file, sep=None, engine='python')
    df = df.where(pd.notna(df), None)  # type: ignore[arg-type]
    records = df.to_dict('records')

    db[collection_name].drop()

    if not records:
        print("⚠ empty, skipped")
        return

    result = db[collection_name].insert_many(records)
    print(f"✓ {len(result.inserted_ids):,} documents")


def _print_summary(db: Database) -> None:
    print(f"\n{'─' * 50}")
    print("Collections:")
    for name in sorted(db.list_collection_names()):
        count = db[name].count_documents({})
        print(f"  {name}: {count:,} documents")


def csv_to_mongodb(
    csv_directory: Path,
    db_name: str,
    connection_string: str,
) -> None:
    csv_files = sorted(csv_directory.glob('*.csv'))

    if not csv_files:
        print(f"No CSV files found in {csv_directory}")
        return

    print(f"Importing {len(csv_files)} file(s) into '{db_name}'\n{'─' * 50}")

    with MongoClient(connection_string) as client:
        db = client[db_name]

        for csv_file in csv_files:
            try:
                _import_csv(db, csv_file)
            except Exception as exc:
                print(f"✗ {exc!s:.80}")

        _print_summary(db)


if __name__ == "__main__":
    csv_to_mongodb(PROCESSED_DIR, DATABASE_NAME, CONNECTION_STRING)