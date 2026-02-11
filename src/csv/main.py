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
    """

    print(f"Processing {len(file_configs)} CSV file(s)\n")

    for config in file_configs:
        try:
            input_file = Path(config['input_file'])
            output_file = Path(config['output_file'])
            columns_to_drop = config.get('columns_to_drop', [])
            columns_to_rename = config.get('columns_to_rename', {})

            print(f"Processing: {input_file.name} -> {output_file.name}")

            # Read the CSV file
            df = pd.read_csv(input_file)
            print(f"  Original shape: {df.shape}")
            print(f"  Original columns: {list(df.columns)}")

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

            # Save the processed file
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
            'columns_to_rename': {
                'Orgnr': 'orgnr',
                'Selskap': 'selskap',
                'Aksjeklasse': 'aksjeklasse',
                'Navn aksjonær': 'aksjonærnavn',
                'Fødselsår/orgnr': 'fødseøsår/orgnr',
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
                'company.org_nr': 'orgnr',
                'company_details.bankrupt_flag': 'konkurs_flagg',
                'company_details.under_forced_liquidation_flag': 'likvidasjon_flagg',
                'nace_code_primary.nace_code': 'nace_kode',
                'organization_type.organization_type_code': 'organisasjonstype',
                'company_establishment.dissolution_date': 'oppløst_dato',
                'company_establishment.establishment_date': 'etablert_dato',
            }
        },
        {
            'input_file': './files/companies_active_companies_pop_100925_v3.csv',
            'output_file': './processed/selskap.csv',
            'columns_to_drop': ['nr'],
            'columns_to_rename': {
                'company.uuid': 'uuid',
                'company.name': 'navn',
                'company.org_nr': 'orgnr',
                'company_details.bankrupt_flag': 'konkurs_flagg',
                'company_details.under_forced_liquidation_flag': 'likvidasjon_flagg',
                'nace_code_primary.nace_code': 'nace_kode',
                'organization_type.organization_type_code': 'organisasjonstype',
                'company_establishment.dissolution_date': 'oppløst_dato',
                'company_establishment.establishment_date': 'etablert_dato',
            }
        },
        {
            'input_file': './files/ownerships_2023_2025.csv',
            'output_file': './processed/eierskap.csv',
            'columns_to_drop': ['unwanted_col'],
            'columns_to_rename': {
                'old_name': 'new_name',
            }
        },
        {
            'input_file': './files/persons_active_companies_pop_100925_v3_keep.csv',
            'output_file': './processed/personer.csv',
            'columns_to_drop': ['unwanted_col'],
            'columns_to_rename': {
                'old_name': 'new_name',
            }
        },
        {
            'input_file': './files/politikere.csv',
            'output_file': './processed/politikere .csv',
            'columns_to_drop': ['unwanted_col'],
            'columns_to_rename': {
                'old_name': 'new_name',
            }
        },
    ]

    process_csv_files(file_configs)