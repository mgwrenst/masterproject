from pathlib import Path

import pandas as pd
from pymongo import MongoClient
from pymongo.database import Database

BASE_DIR = Path(__file__).parent.parent
PROCESSED_DIR = BASE_DIR / "csv" / "processed"

CONNECTION_STRING = "mongodb://localhost:27017"
DATABASE_NAME = "groundtruth"


def import_csv_file(db: Database, csv_file: Path) -> int:
    collection_name = csv_file.stem

    df = pd.read_csv(csv_file, sep=None, engine="python")
    df = df.where(pd.notna(df), None)  # type: ignore[arg-type]
    records = df.to_dict("records")

    db[collection_name].drop()

    if not records:
        return 0

    result = db[collection_name].insert_many(records)
    return len(result.inserted_ids)


def print_database_summary(db: Database) -> None:
    for name in sorted(db.list_collection_names()):
        count = db[name].count_documents({})
        print(f"  {name}: {count:,} documents")


def import_csv_directory(
    csv_directory: Path,
    db_name: str,
    connection_string: str,
) -> None:
    csv_files = sorted(csv_directory.glob("*.csv"))

    if not csv_files:
        print(f"No CSV files found in {csv_directory}")
        return

    with MongoClient(connection_string) as client:
        db = client[db_name]
        imported_files = 0
        imported_documents = 0
        skipped_files = []
        failed_files = []

        for csv_file in csv_files:
            try:
                inserted = import_csv_file(db, csv_file)
            except Exception as exc:
                failed_files.append((csv_file.name, str(exc)))
                continue

            if inserted == 0:
                skipped_files.append(csv_file.name)
                continue

            imported_files += 1
            imported_documents += inserted

        print(f"Imported {imported_files}/{len(csv_files)} CSV files into '{db_name}'.")
        print(f"Inserted {imported_documents:,} documents.")

        if skipped_files:
            print(f"Skipped {len(skipped_files)} empty file(s): {', '.join(skipped_files)}")

        if failed_files:
            print("Failed files:")
            for file_name, error in failed_files:
                print(f"  {file_name}: {error[:100]}")

        print("Collections:")
        print_database_summary(db)


def csv_to_mongodb(csv_directory: Path, db_name: str, connection_string: str) -> None:
    import_csv_directory(csv_directory, db_name, connection_string)


if __name__ == "__main__":
    csv_to_mongodb(PROCESSED_DIR, DATABASE_NAME, CONNECTION_STRING)
