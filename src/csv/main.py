import pandas as pd
from pathlib import Path


def process_csv_files(file_configs):
    """
    Process multiple CSV files with individual configurations for each file.

    Parameters:
    -----------
    file_configs : list of dict
        List of configuration dictionaries, each containing:
        - 'input_file': str, path to the input CSV file
        - 'output_file': str, path/name for the output CSV file
        - 'columns_to_drop': list, optional - columns to drop
        - 'columns_to_rename': dict, optional - {old_name: new_name}
        - 'delimiter': str, optional - delimiter to use (default: ',')
    """

    print(f"Processing {len(file_configs)} CSV file(s)\n")

    for config in file_configs:
        try:
            input_file = Path(config['input_file'])
            output_file = Path(config['output_file'])
            columns_to_drop = config.get('columns_to_drop', [])
            columns_to_rename = config.get('columns_to_rename', {})
            delimiter = config.get('delimiter', ',')  # Default to comma

            print(f"Processing: {input_file.name} -> {output_file.name}")

            # Read the CSV file with specified delimiter
            df = pd.read_csv(input_file, delimiter=delimiter)

            print(f"  Original shape: {df.shape}")
            print(f"  Original columns: {list(df.columns)}")

            # Drop 'Unnamed: 0' if it exists (this is usually an index column)
            if 'Unnamed: 0' in df.columns:
                df = df.drop(columns=['Unnamed: 0'])
                print(f"  Dropped index column: 'Unnamed: 0'")

            # Drop columns if specified
            if columns_to_drop:
                cols_to_drop = [col for col in columns_to_drop if col in df.columns]
                if cols_to_drop:
                    df = df.drop(columns=cols_to_drop)
                    print(f"  Dropped columns: {cols_to_drop}")

            # Rename columns if specified
            if columns_to_rename:
                rename_dict = {k: v for k, v in columns_to_rename.items() if k in df.columns}
                if rename_dict:
                    df = df.rename(columns=rename_dict)
                    print(f"  Renamed columns: {rename_dict}")

            print(f"  New shape: {df.shape}")
            print(f"  New columns: {list(df.columns)}")

            # Create output directory if it doesn't exist
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Save the processed file (always use comma as delimiter for output)
            df.to_csv(output_file, index=False)
            print(f"  Saved to: {output_file}\n")

        except Exception as e:
            print(f"  Error processing {config.get('input_file', 'unknown')}: {str(e)}\n")
            continue

    print("All files processed!")


# Configuration - Customize this section for your files
if __name__ == "__main__":
    file_configs = [
        {
            'input_file': './files/aksjeeiebok.csv',
            'output_file': './processed/aksjeeiebok.csv',
            'delimiter': ';',  # Semicolon delimiter
            'columns_to_rename': {
                'Orgnr': 'orgNr',
                'Selskap': 'selskap',
                'Aksjeklasse': 'aksjeklasse',
                'Navn aksjonær': 'aksjonærNavn',
                'Fødselsår/orgnr': 'fødselsår',
                'Postnr/sted': 'postnr/sted',
                'Landkode': 'landkode',
                'Antall aksjer': 'antallAksjer',
                'Antall aksjer selskap': 'antallAksjerSelskap',
                'År': 'år'
            }
        },
        {
            'input_file': './files/bankrupt_2020_120925.csv',
            'output_file': './processed/konkurs.csv',
            'columns_to_drop': ['nr'],
            'columns_to_rename': {
                'company.uuid': 'uuid',
                'company.name': 'navn',
                'company.org_nr': 'orgNr',
                'company_details.bankrupt_flag': 'konkursFlagg',
                'company_details.under_forced_liquidation_flag': 'likvidasjonFlagg',
                'nace_code_primary.nace_code': 'naceKode',
                'organization_type.organization_type_code': 'organisasjonstype',
                'company_establishment.dissolution_date': 'oppløstDato',
                'company_establishment.establishment_date': 'etablertDato',
            }
        },
        {
            'input_file': './files/companies_active_companies_pop_100925_v3.csv',
            'output_file': './processed/selskap.csv',
            'columns_to_drop': ['nr'],
            'columns_to_rename': {
                'company.uuid': 'uuid',
                'company.name': 'navn',
                'company.org_nr': 'orgNr',
                'company_details.bankrupt_flag': 'konkursFlagg',
                'company_details.under_forced_liquidation_flag': 'likvidasjonFlagg',
                'nace_code_primary.nace_code': 'naceKode',
                'organization_type.organization_type_code': 'organisasjonstype',
                'company_establishment.dissolution_date': 'oppløstDato',
                'company_establishment.establishment_date': 'etablertDato',
            }
        },
        {
            'input_file': './files/ownerships_2023_2025.csv',
            'output_file': './processed/eierskap.csv',
            'columns_to_drop': ['nr',
                                'shareholder_person.birth_month',
                                'shareholder_person.birth_day',
                                'company_share_ownership.ownership_lower',
                                'company_share_ownership.ownership_upper',
                                'company_share_ownership.voting_ownership_lower',
                                'company_share_ownership.voting_ownership_upper',
                                'company_share_ownership_share_issuer_company_uuid',
                                'company_share_ownership.shareholder_person_uuid',
                                'company_share_ownership.shareholder_company_uuid',
                                'company_share_ownership.share_issuer_company_uuid'],
            'columns_to_rename': {
                'shareholder_person.uuid': 'eierPersonUUID',
                'shareholder_person.full_name': 'eierPersonNavn',
                'shareholder_person.birth_date': 'eierPersonFødselsdato',
                'shareholder_person.birth_year': 'eierPersonFødselsår',
                'shareholder_person.gender_uuid': 'eierPersonKjønnUUID',
                'shareholder_person.postal_code': 'eierPersonPostkode',
                'shareholder_person.postal_place': 'eierPersonPoststed',
                'shareholder_person.street_address': 'eierPersonAdresse',
                'shareholder_person.municipality_code': 'eierPersonKommuneNr',
                'shareholder_person.municipality_name': 'eierPersonKommune',

                # Shareholder company
                'shareholder_company.name': 'eierSelskapNavn',
                'shareholder_company.uuid': 'eierSelskapUUID',
                'shareholder_company.org_nr': 'eierSelskapOrgNr',

                # Share issuer company
                'share_issuer_company.name': 'utstederNavn',
                'share_issuer_company.uuid': 'utstederUUID',
                'share_issuer_company.org_nr': 'utstederOrgNr',

                # Company share ownership
                'company_share_ownership.uuid': 'eierskapUUID',
                'company_share_ownership.year': 'eierskapår',
                'company_share_ownership.ownership': 'eierskapAndel',
                'company_share_ownership.share_count': 'eierskapAntall',
                'company_share_ownership.shareholder_name': 'eierskapAksjonær',
                'company_share_ownership.voting_ownership': 'eierskapStemmeandel',
                'company_share_ownership.total_share_count': 'eierskapTotalAntall',
                'company_share_ownership.voting_share_count': 'eierskapStemmeantall',
                'company_share_ownership.total_voting_share_count': 'eierskapTotalStemmeantall',
            }
        },
        {
            'input_file': './files/persons_active_companies_pop_100925_v3_keep.csv',
            'output_file': './processed/personer.csv',
            'columns_to_drop': ['nr',
                                'person.birth_day',
                                'person.birth_month',
                                'person.surrogate_key',
                                'person.surrugate_key',
                                'person.data_origin_ids',
                                'person.disambiguate_uuid',
                                'person.person_location_type_key',
                                'person.national_identification_number',
                                'person.national_identification_schema',
                                'person_company_role.meta.role_elector_id',
                                'person_company_role.meta.role_responsibility',
                                'person_company_role.meta.role_responsibility_percentage',
                                'person_company_role.external_url',
                                'person_company_role.resigned_flag',
                                'person_company_role.surrogate_key',
                                'person_company_role.surrugate_key',
                                'person_company_role.data_source_uuid',
                                'person.street_name',
                                'person.street_letter',
                                'person.street_number',
                                'person.person_master_uuid',
                                'person.composite_business_key',
                                'company.org_nr_schema',
                                'person_company_role.to_date',
                                'person_company_role.business_key',
                                'person_company_role.person_uuid',
                                'person_company_role.company_uuid',
                                'person_company_role.company_role_uuid',
                                'person_company_role.insert_timestamp',
                                'person_company_role.update_timestamp'],
            'columns_to_rename': {
                'person.uuid': 'UUID',
                'person.full_name': 'navn',
                'person.birth_date': 'fødselsdato',
                'person.birth_year': 'fødselsår',
                'person.gender_uuid': 'kjønnUUID',
                'person.postal_code': 'postnummer',
                'person.country_name': 'land',
                'person.postal_place': 'poststed',
                'person.street_address': 'adresse',
                'person.country_code_two': 'landkode',
                'person.insert_timestamp': 'registrertTid',
                'person.update_timestamp': 'oppdatertTid',
                'person.municipality_code': 'kommuneNr',
                'person.municipality_name': 'kommuneNavn',
                'company.name': 'selskapNavn',
                'company.uuid': 'selskapUUID',
                'company.org_nr': 'selskapOrgNr',
                'company.insert_timestamp': 'selskapRegistrert',
                'company.update_timestamp': 'selskapOppdatert',
                'company_role.uuid': 'selskapRolleUUID',
                'company_role.company_role_key': 'selskapRolle',
                'company_role.insert_timestamp': 'rolleRegistrert',
                'company_role.update_timestamp': 'rolleOppdatert',
                'company_role.company_role_rank': 'selskapRolleRang',
                'person_company_role.uuid': 'rolleUUID',
                'person_company_role.from_date': 'rolleSluttdato',
                'person_company_role.business_key': 'rolleStartdato',
            }
        },
        {
            'input_file': './files/politikere.csv',
            'output_file': './processed/politikere.csv',
            'delimiter': ';',  # Semicolon delimiter
        },
    ]

    process_csv_files(file_configs)