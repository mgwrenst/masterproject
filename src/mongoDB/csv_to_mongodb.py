import pandas as pd
from pymongo import MongoClient
from pathlib import Path

def csv_to_mongodb(csv_directory, db_name, connection_string):
    client = MongoClient(connection_string)
    db = client[db_name]

    csv_files = list(Path(csv_directory).glob('*.csv'))

    if not csv_files:
        print(f"No CSV files found in {csv_directory}")
        client.close()
        return

    print(f"Found {len(csv_files)} CSV files\n")

    for csv_file in csv_files:
        collection_name = csv_file.stem
        print(f"Importing {csv_file.name}...", end=" ")

        try:
            # Auto-detect delimiter (comma, semicolon, tab, etc.)
            df = pd.read_csv(csv_file, sep=None, engine='python')

            # Handle NaN values
            df = df.where(pd.notna(df), None)

            # Convert to dict
            records = df.to_dict('records')

            # Drop and insert
            db[collection_name].drop()

            if records:
                result = db[collection_name].insert_many(records)
                print(f"✓ {len(result.inserted_ids)} documents")
            else:
                print(f"⚠ Empty")

        except Exception as e:
            print(f"✗ {str(e)[:60]}")

    # Summary
    print(f"\n{'=' * 60}")
    print("Collections created:")
    for coll in sorted(db.list_collection_names()):
        count = db[coll].count_documents({})
        print(f"  📁 {coll}: {count:,} documents")

    client.close()


if __name__ == "__main__":
    csv_directory = "C:\\Users\\wren9\\PycharmProjects\\masterproject\\src\\csv\\processed"
    database_name = "init_groundtruth"
    connection_string = "mongodb://localhost:27017"

    csv_to_mongodb(csv_directory, database_name, connection_string)