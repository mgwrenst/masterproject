"""
MongoDB Database Restructuring Tool - Complete Configuration
All field names in lowercase, with logical nesting for related data
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from datetime import datetime


# ============================================================
# OPERATION TOGGLES - ENABLE/DISABLE SPECIFIC OPERATIONS
# ============================================================

OPERATIONS_ENABLED = {
    'copy_collections': True,      # Copy all collections from source to target
    'rename_collections': True,    # Rename collections
    'delete_fields': True,         # Remove unwanted fields
    'rename_fields': True,         # Rename fields
    'create_nested_fields': True,  # Create nested/embedded documents
    'combine_collections': True,   # Merge collections together
}


# ============================================================
# CONFIGURATION - EDIT THESE SECTIONS
# ============================================================

# 1. COLLECTION RENAMING
# Format: {'old_name': 'new_name'}
COLLECTION_RENAMES = {
    'bankrupt_2020_120925': 'konkurs',
    'companies_active_companies_pop_100925_v3': 'selskap',
    'persons_active_companies_pop_100925_v3_keep': 'personer',
    'ownerships_2023_2025': 'eierskap',
}


# 2. FIELD RENAMING - ALL LOWERCASE
# Format: {'collection_name': {'old_field': 'new_field'}}
FIELD_RENAMES = {
    'aksjeeiebok': {
        'Orgnr': 'orgnr',
        'Selskap': 'selskap',
        'Aksjeklasse': 'aksjeklasse',
        'Navn aksjonær': 'aksjonærnavn',
        'Fødselsår/orgnr': 'fødselsår/orgnr',
        'Postnr/sted': 'postnr/sted',
        'Landkode': 'landkode',
        'Antall aksjer': 'antallAksjer',
        'Antall aksjer selskap': 'antallAksjerSelskap',
        'År': 'år'

    },
    'politikere': {
        'endelig_Rangering': 'endeligRangering',
    },
    'selskap': {
        'company.uuid': 'uuid',
        'company.name': 'navn',
        'company.org_nr': 'orgnr',
        'company_details.bankrupt_flag': 'konkurs_flagg',
        'company_details.under_forced_liquidation_flag': 'likvidasjon_flagg',
        'nace_code_primary.nace_code': 'nace_kode',
        'organization_type.organization_type_code': 'organisasjonstype',
        'company_establishment.dissolution_date': 'oppløst_dato',
        'company_establishment.establishment_date': 'etablert_dato',
    },
    'konkurs': {
        'company.uuid': 'uuid',
        'company.name': 'navn',
        'company.org_nr': 'orgnr',
        'company_details.bankrupt_flag': 'konkurs_flagg',
        'company_details.under_forced_liquidation_flag': 'likvidasjon_flagg',
        'nace_code_primary.nace_code': 'nace_kode',
        'organization_type.organization_type_code': 'organisasjonstype',
        'company_establishment.dissolution_date': 'oppløst_dato',
        'company_establishment.establishment_date': 'etablert_dato',
    },
    'personer': {
        'person.uuid': 'uuid',
        'person.full_name': 'navn',
        'person.birth_date': 'fødselsdato',
        'person.birth_year': 'fødselsår',
        'person.gender_uuid': 'kjønn_uuid',
        'person.postal_code': 'postnummer',
        'person.country_name': 'land',
        'person.postal_place': 'poststed',
        'person.street_address': 'adresse',
        'person.country_code_two': 'landkode',
        'registrertTid': 'registrert_tid',
        'oppdatertTid': 'oppdatert_tid',
        'kommuneNr': 'kommune_nr',
        'kommuneNavn': 'kommune_navn',
        'selskapNavn': 'selskap_navn',
        'selskapUUID': 'selskap_uuid',
        'selskapOrgNr': 'selskap_orgnr',
        'selskapRegistrert': 'selskap_registrert',
        'selskapOppdatert': 'selskap_oppdatert',
        'selskapRolleUUID': 'selskap_rolle_uuid',
        'selskapRolle': 'selskap_rolle',
        'rolleRegistrert': 'rolle_registrert',
        'rolleOppdatert': 'rolle_oppdatert',
        'selskapRolleRang': 'selskap_rolle_rang',
        'rolleUUID': 'rolle_uuid',
        'rolleSluttdato': 'rolle_sluttdato',
        'rolleStartdato': 'rolle_startdato',
    },
    'eierskap': {
    # Shareholder person
    'shareholder_person.uuid': 'eierpersonuuid',
    'shareholder_person.full_name': 'eierpersonnavn',
    'shareholder_person.birth_date': 'eierpersonfødselsdato',
    'shareholder_person.birth_year': 'eierpersonfødselsår',
    'shareholder_person.birth_month': 'eierpersonfødselsmåned',
    'shareholder_person.birth_day': 'eierpersonfødselsdag',
    'shareholder_person.gender_uuid': 'eierpersonkjønn_uuid',
    'shareholder_person.postal_code': 'eierpersonpostkode',
    'shareholder_person.postal_place': 'eierpersonpoststed',
    'shareholder_person.street_address': 'eierpersonadresse',
    'shareholder_person.municipality_code': 'eierpersonkommunenr',
    'shareholder_person.municipality_name': 'eierpersonkommune',

    # Shareholder company
    'shareholder_company.name': 'aksjonær_selskapnavn',
    'shareholder_company.uuid': 'aksjonær_selskap_uuid',
    'shareholder_company.org_nr': 'aksjonær_selskap_orgnr',

    # Share issuer company
    'share_issuer_company.name': 'utsteder_navn',
    'share_issuer_company.uuid': 'utsteder_uuid',
    'share_issuer_company.org_nr': 'utsteder_orgnr',

    # Company share ownership
    'company_share_ownership.uuid': 'eierskap_uuid',
    'company_share_ownership.year': 'eierskapsår',
    'company_share_ownership.ownership': 'eierandel',
    'company_share_ownership.share_count': 'antall_aksjer',
    'company_share_ownership.ownership_lower': 'eierandel_nedre',
    'company_share_ownership.ownership_upper': 'eierandel_øvre',
    'company_share_ownership.shareholder_name': 'aksjonær_navn',
    'company_share_ownership.voting_ownership': 'stemmeandel',
    'company_share_ownership.total_share_count': 'totalt_antall_aksjer',
    'company_share_ownership.voting_share_count': 'antall_stemmeaksjer',
    'company_share_ownership.voting_ownership_lower': 'stemmeandel_nedre',
    'company_share_ownership.voting_ownership_upper': 'stemmeandel_øvre',
    'company_share_ownership.shareholder_person_uuid': 'aksjonær_person_uuid',
    'company_share_ownership.shareholder_company_uuid': 'aksjonær_selskap_uuid',
    'company_share_ownership.total_voting_share_count': 'totalt_antall_stemmeaksjer',
    'company_share_ownership.share_issuer_company_uuid': 'utsteder_uuid',
}

}


# 3. FIELDS TO DELETE
# Format: {'collection_name': ['field1', 'field2', 'field3']}
FIELDS_TO_DELETE = {
    'selskap': [
        'nr',
    ],
    'konkurs': [
        'nr',
    ],
    'person': [
        'nr',
        'person_birth_day',
        'person_birth_month',
        'person_surrogate_key',
        'person_surrugate_key',
        'person_data_origin_ids',
        'person_disambiguate_uuid',
        'person_person_location_type_key',
        'person_national_identification_number',
        'person_national_identification_schema',
        'person_company_role_meta_role_elector_id',
        'person_company_role_meta_role_responsibility',
        'person_company_role_meta_role_responsibility_percentage',
        'person_company_role_external_url',
        'person_company_role_resigned_flag',
        'person_company_role_surrogate_key',
        'person_company_role_surrugate_key',
        'person_company_role_data_source_uuid',
        'person_street_name',
        'person_street_letter',
        'person_street_number',
        'person_person_master_uuid',
        'person_composite_business_key',
        'company_org_nr_schema',
        'person_company_role_business_key',
        'personSelskapRollePersonUUID',
        'personSelskapRolleSelskapUUID',
        'personSelskapRolleSelskapRolleUUID',
        'personSelskapRolleRegistrertTid',
        'personSelskapRolleOppdatertTid',
    ],
    'eierskap': [
        'nr',
        'shareholder_person_birth_month',
        'shareholder_person_birth_day',
        'company_share_ownership_ownership_lower',
        'company_share_ownership_ownership_upper',
        'company_share_ownership_voting_ownership_lower',
        'company_share_ownership_voting_ownership_upper',
        'company_share_ownership_share_issuer_company_uuid',
        'company_share_ownership_shareholder_person_uuid',
        'company_share_ownership_shareholder_company_uuid',
    ],
}


# 4. COLLECTIONS TO COMBINE
# Format: [{'source': 'collection_to_merge', 'target': 'collection_to_merge_into', 'unique_field': 'field_for_deduplication'}]
COLLECTIONS_TO_COMBINE = [
    {
        'source': 'konkurs',
        'target': 'selskap',
        'unique_field': 'uuid',  # Skip documents with duplicate UUIDs
    },
]


# 5. NESTED FIELDS - Create nested/embedded documents
# Format: {'collection_name': [{'new_field': 'name', 'fields_to_nest': [...], 'delete_original': True/False}]}
NESTED_FIELDS = {
    # Person: Nest address information
    'person': [
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

    # Eierskap: Nest owner person information
    'eierskap': [
        {
            'new_field': 'eier_person',
            'fields_to_nest': ['eier_person_uuid', 'eier_person_navn', 'eier_person_fødselsdato', 'eier_person_fødselsår', 'eier_person_kjønn_uuid', 'eier_person_postkode', 'eier_person_poststed', 'eier_person_adresse', 'eier_person_kommune_nr', 'eier_person_kommune'],
            'delete_original': True
        },
        {
            'new_field': 'eier_selskap',
            'fields_to_nest': ['eier_selskap_uuid', 'eier_selskap_navn', 'eier_selskap_orgnr'],
            'delete_original': True
        },
        {
            'new_field': 'utsteder',
            'fields_to_nest': ['utsteder_uuid', 'utsteder_navn', 'utsteder_orgnr'],
            'delete_original': True
        },
        {
            'new_field': 'eierskap_detaljer',
            'fields_to_nest': ['andel', 'antall', 'aksjonær', 'stemmeandel', 'stemmeantall', 'total_antall', 'total_stemmeantall'],
            'delete_original': True
        },
    ],

    # Selskap: Nest status flags
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

    # Politikere: Nest election information
    'politikere': [
        {
            'new_field': 'kommune_info',
            'fields_to_nest': ['kommune_nr', 'kommune'],
            'delete_original': True
        },
        {
            'new_field': 'valg_info',
            'fields_to_nest': ['listeplass', 'stemmetillegg', 'personstemmer', 'slengere', 'endelig_rangering', 'innvalgt'],
            'delete_original': True
        },
    ],
}


# ============================================================
# OPERATION FUNCTIONS
# ============================================================

def copy_collections(source_db, target_db):
    """Copy all collections from source to target database."""
    print("="*70)
    print("OPERATION: Copy Collections")
    print("="*70 + "\n")

    source_collections = source_db.list_collection_names()

    for collection_name in source_collections:
        print(f"  Copying {collection_name}...", end=" ")

        documents = list(source_db[collection_name].find())

        if documents:
            # Remove unnamed fields
            cleaned_docs = []
            for doc in documents:
                cleaned_doc = {k: v for k, v in doc.items()
                              if k and not k.startswith('Unnamed') and k.strip()}
                cleaned_docs.append(cleaned_doc)

            target_db[collection_name].insert_many(cleaned_docs)
            print(f"✓ {len(cleaned_docs):,} documents")
        else:
            print("⚠ Empty")

    print()


def rename_collections(target_db, renames):
    """Rename collections based on configuration."""
    print("="*70)
    print("OPERATION: Rename Collections")
    print("="*70 + "\n")

    if not renames:
        print("  ℹ No collections to rename\n")
        return

    for old_name, new_name in renames.items():
        if old_name in target_db.list_collection_names():
            target_db[old_name].rename(new_name)
            print(f"  ✓ {old_name} → {new_name}")
        else:
            print(f"  ⚠ {old_name} not found, skipping")

    print()


def delete_fields(target_db, fields_config):
    """Delete unwanted fields from collections."""
    print("="*70)
    print("OPERATION: Delete Fields")
    print("="*70 + "\n")

    if not fields_config:
        print("  ℹ No fields to delete\n")
        return

    for collection_name, fields in fields_config.items():
        if collection_name in target_db.list_collection_names():
            unset_dict = {field: '' for field in fields}
            result = target_db[collection_name].update_many({}, {'$unset': unset_dict})
            print(f"  ✓ {collection_name}: Removed {len(fields)} fields from {result.modified_count:,} documents")
        else:
            print(f"  ⚠ {collection_name} not found, skipping")

    print()


def rename_fields(target_db, field_renames):
    """Rename fields in collections."""
    print("="*70)
    print("OPERATION: Rename Fields")
    print("="*70 + "\n")

    if not field_renames:
        print("  ℹ No fields to rename\n")
        return

    for collection_name, field_mapping in field_renames.items():
        if collection_name in target_db.list_collection_names():
            print(f"  {collection_name}:")
            renamed_count = 0
            for old_field, new_field in field_mapping.items():
                result = target_db[collection_name].update_many(
                    {old_field: {'$exists': True}},
                    {'$rename': {old_field: new_field}}
                )
                if result.modified_count > 0:
                    renamed_count += 1
            print(f"    ✓ Renamed {renamed_count} fields")
        else:
            print(f"  ⚠ {collection_name} not found, skipping")

    print()


def create_nested_fields(target_db, nested_config):
    """Create nested/embedded documents."""
    print("="*70)
    print("OPERATION: Create Nested Fields")
    print("="*70 + "\n")

    if not nested_config:
        print("  ℹ No nested fields to create\n")
        return

    for collection_name, nesting_configs in nested_config.items():
        if collection_name in target_db.list_collection_names():
            print(f"  {collection_name}:")

            for config in nesting_configs:
                new_field = config['new_field']
                fields_to_nest = config['fields_to_nest']
                delete_original = config.get('delete_original', False)

                # Get all documents
                documents = list(target_db[collection_name].find())
                modified_count = 0

                for doc in documents:
                    # Create nested object
                    nested_obj = {}
                    has_data = False

                    for field in fields_to_nest:
                        if field in doc:
                            nested_obj[field] = doc[field]
                            has_data = True

                    # Only update if there's data to nest
                    if has_data:
                        # Update document with nested field
                        update_operation = {'$set': {new_field: nested_obj}}

                        # Optionally delete original fields
                        if delete_original:
                            unset_dict = {field: '' for field in fields_to_nest}
                            update_operation['$unset'] = unset_dict

                        target_db[collection_name].update_one(
                            {'_id': doc['_id']},
                            update_operation
                        )
                        modified_count += 1

                action = "moved to nested" if delete_original else "copied to nested"
                print(f"    ✓ '{new_field}': {len(fields_to_nest)} fields {action} ({modified_count:,} docs)")
        else:
            print(f"  ⚠ {collection_name} not found, skipping")

    print()


def combine_collections(target_db, combine_config):
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

        if source_coll not in target_db.list_collection_names():
            print(f"  ⚠ Source '{source_coll}' not found, skipping")
            continue

        if target_coll not in target_db.list_collection_names():
            print(f"  ⚠ Target '{target_coll}' not found, skipping")
            continue

        # Get existing unique values to avoid duplicates
        existing_values = set()
        if unique_field:
            for doc in target_db[target_coll].find({}, {unique_field: 1}):
                if unique_field in doc:
                    existing_values.add(doc[unique_field])

        # Get documents from source
        source_docs = list(target_db[source_coll].find())

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
            target_db[target_coll].insert_many(docs_to_insert)

        # Drop source collection
        target_db[source_coll].drop()

        print(f"  ✓ Merged {source_coll} → {target_coll}")
        print(f"    Added: {len(docs_to_insert):,} documents")
        if skipped > 0:
            print(f"    Skipped: {skipped:,} duplicates")
        print(f"    Total in {target_coll}: {target_db[target_coll].count_documents({}):,}")

    print()


# ============================================================
# MAIN RESTRUCTURING LOGIC
# ============================================================

def restructure_database(source_db_name, target_db_name, connection_string='mongodb://localhost:27017'):
    """
    Restructure MongoDB database based on enabled operations.
    """
    client = MongoClient(connection_string)
    source_db = client[source_db_name]
    target_db = client[target_db_name]

    print("\n" + "="*70)
    print("MongoDB Database Restructuring")
    print("="*70)
    print(f"Source: {source_db_name}")
    print(f"Target: {target_db_name}")
    print("="*70 + "\n")

    # Check if target exists
    target_exists = target_db_name in client.list_database_names()

    if target_exists and OPERATIONS_ENABLED['copy_collections']:
        print(f"⚠️  WARNING: Database '{target_db_name}' already exists!")
        print(f"   The 'copy_collections' operation will DROP and recreate it.")
        response = input("   Continue? (yes/no): ")
        if response.lower() not in ['yes', 'y', 'ja', 'j']:
            print("Operation cancelled.")
            client.close()
            return
        client.drop_database(target_db_name)
        print(f"   ✓ Dropped existing database\n")
        target_db = client[target_db_name]  # Recreate reference

    elif not target_exists and not OPERATIONS_ENABLED['copy_collections']:
        print(f"❌ ERROR: Target database '{target_db_name}' does not exist!")
        print(f"   You must enable 'copy_collections' to create it first.")
        client.close()
        return

    # Show enabled operations
    enabled_ops = [op for op, enabled in OPERATIONS_ENABLED.items() if enabled]
    print("Enabled operations:")
    for op in enabled_ops:
        print(f"  ✓ {op}")
    print()

    # Execute enabled operations in order
    if OPERATIONS_ENABLED['copy_collections']:
        copy_collections(source_db, target_db)

    if OPERATIONS_ENABLED['rename_collections']:
        rename_collections(target_db, COLLECTION_RENAMES)

    if OPERATIONS_ENABLED['delete_fields']:
        delete_fields(target_db, FIELDS_TO_DELETE)

    if OPERATIONS_ENABLED['rename_fields']:
        rename_fields(target_db, FIELD_RENAMES)

    if OPERATIONS_ENABLED['create_nested_fields']:
        create_nested_fields(target_db, NESTED_FIELDS)

    if OPERATIONS_ENABLED['combine_collections']:
        combine_collections(target_db, COLLECTIONS_TO_COMBINE)

    # Summary
    print("="*70)
    print("Restructuring Complete!")
    print("="*70 + "\n")

    print(f"Collections in '{target_db_name}':\n")
    for collection_name in sorted(target_db.list_collection_names()):
        count = target_db[collection_name].count_documents({})
        indexes = target_db[collection_name].index_information()

        sample = target_db[collection_name].find_one()
        if sample:
            fields = [k for k in sample.keys() if k != '_id']

            print(f"📁 {collection_name}")
            print(f"   Documents: {count:,}")
            print(f"   Indexes: {len(indexes)}")
            print(f"   Fields ({len(fields)}): {', '.join(fields[:8])}", end="")
            if len(fields) > 8:
                print(f", ... +{len(fields) - 8} more")
            else:
                print()
            print()

    print(f"✓ Original database '{source_db_name}' unchanged")
    print(f"✓ Database '{target_db_name}' restructured\n")

    client.close()


# ============================================================
# MAIN EXECUTION
# ============================================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("MongoDB Database Restructuring Tool - Complete Edition")
    print("="*70 + "\n")

    # Show current operation settings
    print("Current operation settings:")
    for op, enabled in OPERATIONS_ENABLED.items():
        status = "✓ ENABLED" if enabled else "✗ DISABLED"
        print(f"  {status:12} - {op}")
    print()

    # Get user input
    source_db = input("Source database name (default: init_groundtruth): ").strip() or "init_groundtruth"
    target_db = input("Target database name (default: groundtruthsmall): ").strip() or "groundtruthsmall"

    if not target_db:
        print("❌ Target database name required!")
        exit(1)

    connection_string = input("MongoDB connection (default: mongodb://localhost:27017): ").strip() or "mongodb://localhost:27017"

    print("\n" + "="*70)
    print("Ready to run with:")
    print("="*70)
    print(f"Source: {source_db}")
    print(f"Target: {target_db}")
    print(f"Connection: {connection_string}")
    print(f"Enabled operations: {sum(OPERATIONS_ENABLED.values())}/{len(OPERATIONS_ENABLED)}")
    print("="*70 + "\n")

    response = input("Continue? (yes/no): ")

    if response.lower() in ['yes', 'y', 'ja', 'j']:
        restructure_database(source_db, target_db, connection_string)
    else:
        print("\nOperation cancelled.")