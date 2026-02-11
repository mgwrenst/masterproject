from pymongo import MongoClient
import pandas as pd


def explore_database(db_name='my_database', connection_string='mongodb://localhost:27017'):
    """Explore the MongoDB database to understand its structure."""
    client = MongoClient(connection_string)
    db = client[db_name]

    print(f"{'=' * 70}")
    print(f"Database: {db_name}")
    print(f"{'=' * 70}\n")

    collections = sorted(db.list_collection_names())

    for collection_name in collections:
        collection = db[collection_name]
        count = collection.count_documents({})

        print(f"\n📁 Collection: {collection_name}")
        print(f"   Documents: {count:,}")

        # Get a sample document
        sample = collection.find_one()

        if sample:
            print(f"   Fields ({len(sample)} total):")
            for key, value in list(sample.items())[:10]:  # Show first 10 fields
                value_type = type(value).__name__
                # Truncate long values
                value_str = str(value)[:50]
                if len(str(value)) > 50:
                    value_str += "..."
                print(f"     - {key}: {value_type} = {value_str}")

            if len(sample) > 10:
                print(f"     ... and {len(sample) - 10} more fields")

        print(f"   {'-' * 66}")

    # Look for potential relationships
    print(f"\n{'=' * 70}")
    print("Potential Relationships (fields that might link collections):")
    print(f"{'=' * 70}\n")

    # Collect all field names across collections
    field_analysis = {}
    for collection_name in collections:
        collection = db[collection_name]
        sample = collection.find_one()
        if sample:
            for field in sample.keys():
                if field != '_id':
                    if field not in field_analysis:
                        field_analysis[field] = []
                    field_analysis[field].append(collection_name)

    # Find fields that appear in multiple collections
    print("Fields appearing in multiple collections:")
    for field, colls in sorted(field_analysis.items()):
        if len(colls) > 1:
            print(f"  🔗 '{field}' appears in: {', '.join(colls)}")

    client.close()


if __name__ == "__main__":
    explore_database('init_groundtruth')