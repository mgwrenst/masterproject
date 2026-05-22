import pandas as pd
import re
from pathlib import Path

# All relative paths resolve from this file's location, not the working
# directory — so the script works regardless of where it is invoked from.
BASE_DIR      = Path(__file__).parent
FILES_DIR     = BASE_DIR / 'files'
PROCESSED_DIR = BASE_DIR / 'processed'
NACE_FILE     = FILES_DIR / 'nace.csv'

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GENDER_UUID_MAP: dict[str, str] = {
    'a091eaef-e659-4920-9bdc-d42a75aab765': 'Mann',
    '27ef7f8e-c23d-424b-8050-667a750b1574': 'Kvinne',
}

# Post-rename columns that contain gender UUIDs -> their human-readable column name
GENDER_COLUMNS: dict[str, str] = {
    'kjønnUUID':            'kjønn',
    'eierPersonKjønnUUID':  'eierPersonKjønn',
}

# Post-rename date columns to convert to ISO 8601 UTC, keyed by output filename
DATE_COLUMNS: dict[str, list[str]] = {
    'personer.csv': [
        'fødselsdato', 'registrertTid', 'oppdatertTid',
        'selskapRegistrert', 'selskapOppdatert',
        'rolleRegistrert', 'rolleOppdatert', 'rolleStartdato', 'rolleSluttdato',
    ],
    'politikere.csv':  ['fødselsdato'],
    'eierskap.csv':    ['eierPersonFødselsdato'],
    'selskap.csv':     ['oppløstDato', 'etablertDato'],
    'tmp_konkurs.csv': ['oppløstDato', 'etablertDato'],
    'tmp_selskap.csv': ['oppløstDato', 'etablertDato'],
}

DAYFIRST_DATE_COLUMNS: dict[str, list[str]] = {
    'politikere.csv': ['fødselsdato'],
}

TITLE_CASE_COLUMNS: dict[str, list[str]] = {
    'aksjeeiebok.csv': ['aksjonærNavn'],
}

COLUMN_RENAME_SELSKAP: dict[str, str] = {
    'company.uuid':                                  'uuid',
    'company.name':                                  'navn',
    'company.org_nr':                                'orgNr',
    'company_details.bankrupt_flag':                 'konkursFlagg',
    'company_details.under_forced_liquidation_flag': 'likvidasjonFlagg',
    'nace_code_primary.nace_code':                   'naceKode',
    'organization_type.organization_type_code':      'organisasjonstype',
    'company_establishment.dissolution_date':        'oppløstDato',
    'company_establishment.establishment_date':      'etablertDato',
}

# ---------------------------------------------------------------------------
# File configurations
# ---------------------------------------------------------------------------

FILE_CONFIGS: list[dict] = [
    {
        'input_file':  'aksjeeiebok.csv',
        'output_file': 'aksjeeiebok.csv',
        'delimiter':   ';',
        'columns_to_rename': {
            'Orgnr':                 'orgNr',
            'Selskap':               'selskap',
            'Aksjeklasse':           'aksjeklasse',
            'Navn aksjonær':         'aksjonærNavn',
            'Fødselsår/orgnr':       'fødselsår',
            'Postnr/sted':           'postnr/sted',
            'Landkode':              'landkode',
            'Antall aksjer':         'antallAksjer',
            'Antall aksjer selskap': 'antallAksjerSelskap',
            'År':                    'år',
        },
    },
    {
        'input_file':  'bankrupt_2020_120925.csv',
        'output_file': 'tmp_konkurs.csv',
        'columns_to_drop': ['nr'],
        'columns_to_rename': COLUMN_RENAME_SELSKAP,
        'add_nace_description': True,
    },
    {
        'input_file':  'companies_active_companies_pop_100925_v3.csv',
        'output_file': 'tmp_selskap.csv',
        'columns_to_drop': ['nr'],
        'columns_to_rename': COLUMN_RENAME_SELSKAP,
        'add_nace_description': True,
    },
    {
        'input_file':  'ownerships_2023_2025.csv',
        'output_file': 'eierskap.csv',
        'columns_to_drop': [
            'nr',
            'shareholder_person.birth_month',
            'shareholder_person.birth_day',
            'company_share_ownership.ownership_lower',
            'company_share_ownership.ownership_upper',
            'company_share_ownership.voting_ownership_lower',
            'company_share_ownership.voting_ownership_upper',
            'company_share_ownership_share_issuer_company_uuid',
            'company_share_ownership.shareholder_person_uuid',
            'company_share_ownership.shareholder_company_uuid',
            'company_share_ownership.share_issuer_company_uuid',
        ],
        'columns_to_rename': {
            'shareholder_person.uuid':                          'eierPersonUUID',
            'shareholder_person.full_name':                     'eierPersonNavn',
            'shareholder_person.birth_date':                    'eierPersonFødselsdato',
            'shareholder_person.birth_year':                    'eierPersonFødselsår',
            'shareholder_person.gender_uuid':                   'eierPersonKjønnUUID',
            'shareholder_person.postal_code':                   'eierPersonPostkode',
            'shareholder_person.postal_place':                  'eierPersonPoststed',
            'shareholder_person.street_address':                'eierPersonAdresse',
            'shareholder_person.municipality_code':             'eierPersonKommuneNr',
            'shareholder_person.municipality_name':             'eierPersonKommune',
            'shareholder_company.name':                         'eierSelskapNavn',
            'shareholder_company.uuid':                         'eierSelskapUUID',
            'shareholder_company.org_nr':                       'eierSelskapOrgNr',
            'share_issuer_company.name':                        'utstederNavn',
            'share_issuer_company.uuid':                        'utstederUUID',
            'share_issuer_company.org_nr':                      'utstederOrgNr',
            'company_share_ownership.uuid':                     'eierskapUUID',
            'company_share_ownership.year':                     'eierskapår',
            'company_share_ownership.ownership':                'eierskapAndel',
            'company_share_ownership.share_count':              'eierskapAntall',
            'company_share_ownership.shareholder_name':         'eierskapAksjonær',
            'company_share_ownership.voting_ownership':         'eierskapStemmeandel',
            'company_share_ownership.total_share_count':        'eierskapTotalAntall',
            'company_share_ownership.voting_share_count':       'eierskapStemmeantall',
            'company_share_ownership.total_voting_share_count': 'eierskapTotalStemmeantall',
        },
    },
    {
        'input_file':  'persons_active_companies_pop_100925_v3_keep.csv',
        'output_file': 'personer.csv',
        'columns_to_drop': [
            'nr',
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
            'person_company_role.business_key',
            'person_company_role.person_uuid',
            'person_company_role.company_uuid',
            'person_company_role.company_role_uuid',
            'person_company_role.insert_timestamp',
            'person_company_role.update_timestamp',
        ],
        'columns_to_rename': {
            'person.uuid':                    'uuid',
            'person.full_name':               'navn',
            'person.birth_date':              'fødselsdato',
            'person.birth_year':              'fødselsår',
            'person.gender_uuid':             'kjønnUUID',
            'person.postal_code':             'postnummer',
            'person.country_name':            'land',
            'person.postal_place':            'poststed',
            'person.street_address':          'adresse',
            'person.country_code_two':        'landkode',
            'person.insert_timestamp':        'registrertTid',
            'person.update_timestamp':        'oppdatertTid',
            'person.municipality_code':       'kommuneNr',
            'person.municipality_name':       'kommuneNavn',
            'company.name':                   'selskapNavn',
            'company.uuid':                   'selskapUUID',
            'company.org_nr':                 'selskapOrgNr',
            'company.insert_timestamp':       'selskapRegistrert',
            'company.update_timestamp':       'selskapOppdatert',
            'company_role.uuid':              'selskapRolleUUID',
            'company_role.company_role_key':  'selskapRolle',
            'company_role.insert_timestamp':  'rolleRegistrert',
            'company_role.update_timestamp':  'rolleOppdatert',
            'company_role.company_role_rank': 'selskapRolleRang',
            'person_company_role.uuid':       'rolleUUID',
            'person_company_role.from_date':  'rolleStartdato',
            'person_company_role.to_date':    'rolleSluttdato',
        },
    },
    {
        'input_file':  'politikere.csv',
        'output_file': 'politikere.csv',
        'delimiter':   ';',
    },
]

# ---------------------------------------------------------------------------
# Processing helpers
# ---------------------------------------------------------------------------

def _normalize_nace_code(value: object) -> str | None:
    if value is None:
        return None

    code = str(value).strip()
    if not code or code.lower() in {'nan', 'none'}:
        return None

    if code.endswith('.0'):
        code = code[:-2]
    return code or None


def _load_nace_descriptions() -> dict[str, str]:
    if not NACE_FILE.exists():
        print(f"    nace   : {NACE_FILE.name} not found")
        return {}

    try:
        nace = pd.read_csv(NACE_FILE, delimiter=';', dtype=str, encoding='utf-8')
    except UnicodeDecodeError:
        nace = pd.read_csv(NACE_FILE, delimiter=';', dtype=str, encoding='cp1252')

    if 'code' not in nace.columns or 'name' not in nace.columns:
        print(f"    nace   : {NACE_FILE.name} is missing code/name columns")
        return {}

    nace['code'] = nace['code'].map(_normalize_nace_code)
    return dict(zip(nace['code'], nace['name']))


def _add_nace_descriptions(df: pd.DataFrame) -> pd.DataFrame:
    if 'naceKode' not in df.columns:
        return df

    descriptions = _load_nace_descriptions()
    if not descriptions:
        return df

    def find_description(code: object) -> str | None:
        normalized_code = _normalize_nace_code(code)
        if normalized_code is None:
            return None
        return descriptions.get(normalized_code)

    df['naceBeskrivelse'] = df['naceKode'].map(find_description)

    columns = [col for col in df.columns if col != 'naceBeskrivelse']
    nace_index = columns.index('naceKode') + 1
    columns.insert(nace_index, 'naceBeskrivelse')

    matched = df['naceBeskrivelse'].notna().sum()
    print(f"    nace   : {matched:,}/{len(df):,} code(s) matched")
    return df[columns]


def _convert_date_columns(df: pd.DataFrame, output_filename: str) -> pd.DataFrame:
    """Convert known date columns to clean UTC ISO 8601 strings for MongoDB."""
    dayfirst_columns = DAYFIRST_DATE_COLUMNS.get(output_filename, [])

    for col in DATE_COLUMNS.get(output_filename, []):
        if col in df.columns:
            df[col] = (
                pd.to_datetime(
                    df[col],
                    utc=True,
                    errors='coerce',
                    dayfirst=col in dayfirst_columns,
                )
                .dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            )
            print(f"    date   : {col}")
    return df


def _map_gender_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Replace gender UUIDs with human-readable labels and rename the columns."""
    for uuid_col, label_col in GENDER_COLUMNS.items():
        if uuid_col in df.columns:
            df[uuid_col] = df[uuid_col].map(GENDER_UUID_MAP)
            df = df.rename(columns={uuid_col: label_col})
            print(f"    gender : {uuid_col!r} -> {label_col!r}")
    return df


def _title_case_name(value: object) -> object:
    if value is None:
        return value

    text = str(value).strip()
    if not text or text.lower() in {'nan', 'none'}:
        return value

    return re.sub(
        r"[^\W\d_]+",
        lambda match: match.group(0).capitalize(),
        text.lower(),
    )


def _title_case_columns(df: pd.DataFrame, output_filename: str) -> pd.DataFrame:
    for col in TITLE_CASE_COLUMNS.get(output_filename, []):
        if col in df.columns:
            df[col] = df[col].map(_title_case_name)
            print(f"    names  : {col}")
    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_csv_files(file_configs: list[dict]) -> None:
    """
    Process multiple CSV files: drop columns, rename columns, map gender
    UUIDs, and convert date columns.

    Each config dict supports:
        input_file        : str  – source path
        output_file       : str  – destination path
        columns_to_drop   : list – columns to remove (optional)
        columns_to_rename : dict – {old: new} renames (optional)
        delimiter         : str  – input delimiter, default ','
        add_nace_description : bool – add NACE description after naceKode
    """
    print(f"Processing {len(file_configs)} file(s)\n{'─' * 50}")

    for config in file_configs:
        input_path  = FILES_DIR     / Path(config['input_file']).name
        output_path = PROCESSED_DIR / Path(config['output_file']).name
        to_drop     = config.get('columns_to_drop', [])
        to_rename   = config.get('columns_to_rename', {})
        delimiter   = config.get('delimiter', ',')

        print(f"\n{input_path.name} -> {output_path.name}")

        try:
            df = pd.read_csv(input_path, delimiter=delimiter)
            print(f"  shape  : {df.shape}")

            # Remove auto-generated index column when present
            if 'Unnamed: 0' in df.columns:
                df = df.drop(columns=['Unnamed: 0'])

            # Drop unwanted columns (silently skip missing ones)
            existing_drops = [c for c in to_drop if c in df.columns]
            if existing_drops:
                df = df.drop(columns=existing_drops)
                print(f"  dropped: {len(existing_drops)} column(s)")

            # Rename columns (silently skip missing ones)
            valid_renames = {k: v for k, v in to_rename.items() if k in df.columns}
            if valid_renames:
                df = df.rename(columns=valid_renames)
                print(f"  renamed: {len(valid_renames)} column(s)")

            if config.get('add_nace_description'):
                df = _add_nace_descriptions(df)

            df = _map_gender_columns(df)
            df = _title_case_columns(df, output_path.name)
            df = _convert_date_columns(df, output_path.name)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(output_path, index=False)
            print(f"  saved  : {output_path}  (shape: {df.shape})")

        except FileNotFoundError:
            print(f"  ✗ File not found, skipping: {input_path}")
        except Exception as exc:
            print(f"  ✗ Error: {exc}")

    print(f"\n{'─' * 50}\nDone.")


def merge_and_cleanup(input_files: list[str], output_file: str) -> None:
    """
    Concatenate CSV files into one, save the result, then delete the sources.

    All input files must share identical columns.
    """
    output_path = Path(output_file)
    print(f"\nMerging {len(input_files)} file(s) -> {output_path.name}")

    frames: list[pd.DataFrame] = []
    paths:  list[Path]         = []

    for path_str in input_files:
        p = Path(path_str)
        if not p.exists():
            print(f"  ⚠ Not found, skipping: {p.name}")
            continue
        df = pd.read_csv(p)
        print(f"  read   : {p.name} ({df.shape[0]:,} rows)")
        frames.append(df)
        paths.append(p)

    if not frames:
        print("  ✗ No files to merge.")
        return

    merged = pd.concat(frames, ignore_index=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)
    print(f"  saved  : {output_path}  ({merged.shape[0]:,} rows)")

    for p in paths:
        p.unlink()
        print(f"  removed: {p.name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    process_csv_files(FILE_CONFIGS)

    merge_and_cleanup(
        input_files=[
            str(PROCESSED_DIR / 'tmp_konkurs.csv'),
            str(PROCESSED_DIR / 'tmp_selskap.csv'),
        ],
        output_file=str(PROCESSED_DIR / 'selskap.csv'),
    )
