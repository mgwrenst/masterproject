"""
MongoDB Database Restructuring Tool - Simplified Version
For databases where fields/collections are already cleaned and renamed
"""

from pymongo import MongoClient


# ============================================================
# OPERATION TOGGLES
# ============================================================

OPERATIONS_ENABLED = {
    'create_nested_fields': False,  # Create nested/embedded documents
    'combine_collections': True,   # Merge collections together
}


# ============================================================
# CONFIGURATION
# ============================================================

# 1. NESTED FIELDS - Create nested/embedded documents
# Format: {'collection_name': [{'new_field': 'name', 'fields_to_nest': [...], 'delete_original': True/False}]}
NESTED_FIELDS = {
    'personer': [
        {
            'new_field': 'adresse_info',
            'fields_to_nest': ['adresse', 'postnummer', 'poststed', 'kommune_nr', 'kommune_navn', 'land', 'landkode'],
            'delete_original': True
        },
        {
            'new_field': 'selskap_info',
            'fields_to_nest': ['selskap_navn', 'selskap_uuid', 'selskap_orgnr', 'selskap_registrert', 'selskap_oppdatert'],
            'delete_original': True
        },
        {
            'new_field': 'rolle_info',
            'fields_to_nest': ['selskap_rolle', 'selskap_rolle_uuid', 'selskap_rolle_rang', 'rolle_uuid', 'rolle_startdato', 'rolle_sluttdato', 'rolle_registrert', 'rolle_oppdatert'],
            'delete_original': True
        },
    ],

    'eierskap': [
        {
            'new_field': 'eier_person',
            'fields_to_nest': ['eierperson_uuid', 'eierperson_navn', 'eierperson_fødselsdato', 'eierperson_fødselsår', 'eierperson_kjønn_uuid', 'eierperson_postkode', 'eierperson_poststed', 'eierperson_adresse', 'eierperson_kommunenr', 'eierperson_kommune'],
            'delete_original': True
        },
        {
            'new_field': 'eier_selskap',
            'fields_to_nest': ['aksjonær_selskap_uuid', 'aksjonær_selskap_navn', 'aksjonær_selskap_orgnr'],
            'delete_original': True
        },
        {
            'new_field': 'utsteder',
            'fields_to_nest': ['utsteder_uuid', 'utsteder_navn', 'utsteder_orgnr'],
            'delete_original': True
        },
        {
            'new_field': 'eierskap_detaljer',
            'fields_to_nest': ['eierskap_år', 'eierandel', 'antall_aksjer', 'aksjonær_navn', 'stemmeandel', 'totalt_antall_aksjer', 'antall_stemmeaksjer', 'totalt_antall_stemmeaksjer'],
            'delete_original': True
        },
    ],

    'selskap': [
        {
            'new_field': 'status',
            'fields_to_nest': ['konkurs_flagg', 'likvidasjon_flagg'],
            'delete_original': True
        },
        {
            'new_field': 'datoer',
            'fields_to_nest': ['etablert_dato', 'oppløst_dato'],
            'delete_original': True
        },
    ],

    'politikere': [
        {
            'new_field': 'kommune_info',
            'fields_to_nest': ['kommune_nr', 'kommune'],
            'delete_original': True
        },
        {
            'new_field': 'valg_info',
            'fields_to_nest': ['listeplass', 'stemmetillegg', 'personstemmer', 'slengere', 'endeligRangering', 'innvalgt'],
            'delete_original': True
        },
    ],
}


# 2. COLLECTIONS TO COMBINE
# Format: [{'source': 'collection_to_merge', 'target': 'collection_to_merge_into', 'unique_field': 'field_for_deduplication'}]
COLLECTIONS_TO_COMBINE = [
    {
        'source': 'konkurs',
        'target': 'selskap',
        'unique_field': 'uuid',
    },
]


# ============================================================
# OPERATION FUNCTIONS
# ============================================================

def create_nested_fields(db, nested_config):
    """Create nested/embedded documents."""
    print("="*70)
    print("OPERATION: Create Nested Fields")
    print("="*70 + "\n")

    if not nested_config:
        print("  ℹ No nested fields to create\n")
        return

    for collection_name, nesting_configs in nested_config.items():
        if collection_name not in db.list_collection_names():
            print(f"  ⚠ {collection_name} not found, skipping")
            continue

        print(f"  {collection_name}:")

        for config in nesting_configs:
            new_field = config['new_field']
            fields_to_nest = config['fields_to_nest']
            delete_original = config.get('delete_original', False)

            documents = list(db[collection_name].find())
            modified_count = 0

            for doc in documents:
                nested_obj = {}
                has_data = False

                for field in fields_to_nest:
                    if field in doc:
                        nested_obj[field] = doc[field]
                        has_data = True

                if has_data:
                    update_operation = {'$set': {new_field: nested_obj}}

                    if delete_original:
                        unset_dict = {field: '' for field in fields_to_nest}
                        update_operation['$unset'] = unset_dict

                    db[collection_name].update_one(
                        {'_id': doc['_id']},
                        update_operation
                    )
                    modified_count += 1

            action = "moved to nested" if delete_original else "copied to nested"
            print(f"    ✓ '{new_field}': {len(fields_to_nest)} fields {action} ({modified_count:,} docs)")

    print()


def combine_collections(db, combine_config):
    """Combine/merge collections together."""
    print("="*70)
    print("OPERATION: Combine Collections")
    print("="*70 + "\n")

    if not combine_config:
        print("  ℹ No collections to combine\n")
        return

    for config in combine_config:
        source_coll = config['source']
        target_coll = config['target']
        unique_field = config.get('unique_field')

        if source_coll not in db.list_collection_names():
            print(f"  ⚠ Source '{source_coll}' not found, skipping")
            continue

        if target_coll not in db.list_collection_names():
            print(f"  ⚠ Target '{target_coll}' not found, skipping")
            continue

        # Get existing unique values to avoid duplicates
        existing_values = set()
        if unique_field:
            for doc in db[target_coll].find({}, {unique_field: 1}):
                if unique_field in doc:
                    existing_values.add(doc[unique_field])

        # Get documents from source
        source_docs = list(db[source_coll].find())

        # Filter out duplicates
        docs_to_insert = []
        skipped = 0

        for doc in source_docs:
            if unique_field and doc.get(unique_field) in existing_values:
                skipped += 1
                continue
            docs_to_insert.append(doc)

        # Insert into target
        if docs_to_insert:
            db[target_coll].insert_many(docs_to_insert)

        # Drop source collection
        db[source_coll].drop()

        print(f"  ✓ Merged {source_coll} → {target_coll}")
        print(f"    Added: {len(docs_to_insert):,} documents")
        if skipped > 0:
            print(f"    Skipped: {skipped:,} duplicates")
        print(f"    Total in {target_coll}: {db[target_coll].count_documents({}):,}")

    print()


# ============================================================
# MAIN LOGIC
# ============================================================

def restructure_database(db_name, connection_string='mongodb://localhost:27017'):
    """
    Restructure MongoDB database based on enabled operations.
    """
    client = MongoClient(connection_string)
    db = client[db_name]

    print("\n" + "="*70)
    print("MongoDB Database Restructuring - Simplified")
    print("="*70)
    print(f"Database: {db_name}")
    print("="*70 + "\n")

    # Check if database exists
    if db_name not in client.list_database_names():
        print(f"❌ ERROR: Database '{db_name}' does not exist!")
        client.close()
        return

    # Show enabled operations
    enabled_ops = [op for op, enabled in OPERATIONS_ENABLED.items() if enabled]
    print("Enabled operations:")
    for op in enabled_ops:
        print(f"  ✓ {op}")
    print()

    # Execute enabled operations
    if OPERATIONS_ENABLED['create_nested_fields']:
        create_nested_fields(db, NESTED_FIELDS)

    if OPERATIONS_ENABLED['combine_collections']:
        combine_collections(db, COLLECTIONS_TO_COMBINE)

    # Summary
    print("="*70)
    print("Restructuring Complete!")
    print("="*70 + "\n")

    print(f"Collections in '{db_name}':\n")
    for collection_name in sorted(db.list_collection_names()):
        count = db[collection_name].count_documents({})
        sample = db[collection_name].find_one()

        if sample:
            fields = [k for k in sample.keys() if k != '_id']
            print(f"📁 {collection_name}")
            print(f"   Documents: {count:,}")
            print(f"   Fields ({len(fields)}): {', '.join(fields[:10])}", end="")
            if len(fields) > 10:
                print(f", ... +{len(fields) - 10} more")
            else:
                print()
            print()

    client.close()


# ============================================================
# MAIN EXECUTION
# ============================================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("MongoDB Database Restructuring Tool - Simplified")
    print("="*70 + "\n")

    db_name = input("Database name (default: groundtruthsmall): ").strip() or "groundtruthsmall"
    connection_string = input("MongoDB connection (default: mongodb://localhost:27017): ").strip() or "mongodb://localhost:27017"

    print("\n" + "="*70)
    print("Ready to run with:")
    print("="*70)
    print(f"Database: {db_name}")
    print(f"Connection: {connection_string}")
    print(f"Operations: {', '.join([op for op, enabled in OPERATIONS_ENABLED.items() if enabled])}")
    print("="*70 + "\n")

    response = input("Continue? (yes/no): ")

    if response.lower() in ['yes', 'y', 'ja', 'j']:
        restructure_database(db_name, connection_string)
    else:
        print("\nOperation cancelled.")