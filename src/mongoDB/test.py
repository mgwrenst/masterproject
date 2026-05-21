"""
migrate_to_groundtruthTest_name_matching.py

Creates a document-oriented MongoDB database called `groundtruthTest`
from the flat source database `groundtruth`.

Main design:
  - selskap: company-centered documents with embedded aksjeeiebok, eierskap and roller
  - personer: person-centered documents with embedded roller and eierskap summaries
  - politicians are matched by normalized name across:
      politikere.navn <-> personer.navn
      politikere.navn <-> eierskap.eierPersonNavn
      politikere.navn <-> aksjeeiebok.aksjonærNavn

Important:
  - Name-only matching is not a verified identity match.
  - The script stores match metadata so this limitation is visible in the data.

Usage:
  python migrate_to_groundtruthTest_name_matching.py --drop
  python migrate_to_groundtruthTest_name_matching.py --drop --verbose
"""

import argparse
import math
import re
from typing import Any, Dict, Iterable, List, Optional
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DocumentTooLarge, BulkWriteError

SOURCE_DB = "groundtruth"
TARGET_DB = "groundtruthTest"
MONGO_URI = "mongodb://localhost:27017"
MAX_COMPANY_ARRAY_ITEMS = 5000


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def clean_value(value: Any) -> Any:
    if isinstance(value, dict):
        return clean_doc(value)
    if isinstance(value, list):
        return [clean_value(v) for v in value]
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def clean_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {key: clean_value(value) for key, value in doc.items()}


def normalize_name(value: Any) -> Optional[str]:
    """Normalize names so uppercase/lowercase differences do not matter."""
    if is_missing(value):
        return None
    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text or None


def birth_year_from_date(value: Any) -> Optional[int]:
    if is_missing(value):
        return None
    text = str(value)
    match = re.search(r"(\d{4})", text)
    if not match:
        return None
    return int(match.group(1))


def safe_int(value: Any) -> Optional[int]:
    if is_missing(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def first_not_missing(*values: Any) -> Any:
    for value in values:
        if not is_missing(value):
            return value
    return None


def verbose_print(verbose: bool, message: str) -> None:
    if verbose:
        print(message)


# -----------------------------------------------------------------------------
# Politician matching
# -----------------------------------------------------------------------------

def make_politiker(doc: Dict[str, Any], match_type: str) -> Dict[str, Any]:
    return clean_doc({
        "erPolitiker": True,
        "partinavn": doc.get("partinavn"),
        "kommune": doc.get("kommune"),
        "kommunenummer": doc.get("kommunenummer"),
        "innvalgt": doc.get("innvalgt"),
        "valg": {
            "listeplass": doc.get("listeplass"),
            "endeligRangering": doc.get("endelig_rangering"),
            "personstemmer": doc.get("personstemmer"),
            "slengere": doc.get("slengere"),
            "stemmetillegg": doc.get("stemmetillegg"),
        },
        "match": {
            "type": match_type,
            "confidence": "medium" if match_type == "navn" else "higher",
            "note": "Matched by available personal fields, not by shared unique identifier.",
        },
    })


def build_politiker_lookup(source) -> Dict[str, List[Dict[str, Any]]]:
    """Map normalized politician name to one or more politician records."""
    lookup: Dict[str, List[Dict[str, Any]]] = {}
    for pol in source["politikere"].find():
        name_key = normalize_name(pol.get("navn"))
        if not name_key:
            continue
        lookup.setdefault(name_key, []).append(pol)
    return lookup


def match_politiker_by_name(
    name: Any,
    politiker_lookup: Dict[str, List[Dict[str, Any]]],
    birth_year: Any = None,
) -> Dict[str, Any]:
    """Match by normalized name. If birth year is available, prefer candidates with same birth year."""
    name_key = normalize_name(name)
    if not name_key or name_key not in politiker_lookup:
        return {"erPolitiker": False}

    candidates = politiker_lookup[name_key]
    input_year = safe_int(birth_year)

    if input_year is not None:
        for candidate in candidates:
            candidate_year = birth_year_from_date(candidate.get("fødselsdato"))
            if candidate_year == input_year:
                return make_politiker(candidate, "navn_fødselsår")

    # Name-only fallback. This is useful for your experiment, but less certain.
    pol = candidates[0]
    result = make_politiker(pol, "navn")
    if len(candidates) > 1:
        result["match"]["ambiguousCandidates"] = len(candidates)
        result["match"]["note"] = "Multiple politicians had the same normalized name. First candidate was used."
    return result


# -----------------------------------------------------------------------------
# Document builders
# -----------------------------------------------------------------------------

def make_company(doc: Dict[str, Any]) -> Dict[str, Any]:
    return clean_doc({
        "_id": doc.get("_id"),
        "uuid": doc.get("uuid"),
        "orgNr": doc.get("orgNr"),
        "navn": doc.get("navn"),
        "organisasjonstype": doc.get("organisasjonstype"),
        "bransje": {"naceKode": doc.get("naceKode")},
        "datoer": {
            "etablertDato": doc.get("etablertDato"),
            "oppløstDato": doc.get("oppløstDato"),
        },
        "status": {
            "konkursFlagg": doc.get("konkursFlagg"),
            "likvidasjonFlagg": doc.get("likvidasjonFlagg"),
        },
        "aksjeeiebok": [],
        "eierskap": [],
        "roller": [],
    })


def person_key_from_role(doc: Dict[str, Any]) -> Optional[str]:
    if not is_missing(doc.get("uuid")):
        return f"uuid:{doc.get('uuid')}"
    name_key = normalize_name(doc.get("navn"))
    if name_key:
        return f"navn:{name_key}"
    return None


def person_key_from_eierskap(doc: Dict[str, Any]) -> Optional[str]:
    if not is_missing(doc.get("eierPersonUUID")):
        return f"uuid:{doc.get('eierPersonUUID')}"
    name_key = normalize_name(doc.get("eierPersonNavn"))
    if name_key:
        return f"navn:{name_key}"
    return None


def make_base_person(doc: Dict[str, Any], politiker_lookup: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    return clean_doc({
        "_id": doc.get("_id"),
        "uuid": doc.get("uuid"),
        "navn": doc.get("navn"),
        "fødselsdato": doc.get("fødselsdato"),
        "fødselsår": doc.get("fødselsår"),
        "kjønn": doc.get("kjønn"),
        "adresse": {
            "gateadresse": doc.get("adresse"),
            "postnummer": doc.get("postnummer"),
            "poststed": doc.get("poststed"),
            "kommuneNavn": doc.get("kommuneNavn"),
            "kommuneNr": doc.get("kommuneNr"),
            "land": doc.get("land"),
            "landkode": doc.get("landkode"),
        },
        "metadata": {
            "registrertTid": doc.get("registrertTid"),
            "oppdatertTid": doc.get("oppdatertTid"),
        },
        "politiker": match_politiker_by_name(doc.get("navn"), politiker_lookup, doc.get("fødselsår")),
        "roller": [],
        "eierskap": [],
        "aksjeeiebok": [],
    })


def make_person_from_eierskap(doc: Dict[str, Any], politiker_lookup: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    return clean_doc({
        "uuid": doc.get("eierPersonUUID"),
        "navn": doc.get("eierPersonNavn"),
        "fødselsdato": doc.get("eierPersonFødselsdato"),
        "fødselsår": doc.get("eierPersonFødselsår"),
        "kjønn": doc.get("eierPersonKjønn"),
        "adresse": {
            "gateadresse": doc.get("eierPersonAdresse"),
            "postnummer": doc.get("eierPersonPostkode"),
            "poststed": doc.get("eierPersonPoststed"),
            "kommuneNavn": doc.get("eierPersonKommune"),
            "kommuneNr": doc.get("eierPersonKommuneNr"),
        },
        "politiker": match_politiker_by_name(doc.get("eierPersonNavn"), politiker_lookup, doc.get("eierPersonFødselsår")),
        "roller": [],
        "eierskap": [],
        "aksjeeiebok": [],
    })


def make_person_from_politiker(pol: Dict[str, Any]) -> Dict[str, Any]:
    return clean_doc({
        "navn": pol.get("navn"),
        "fødselsdato": pol.get("fødselsdato"),
        "fødselsår": birth_year_from_date(pol.get("fødselsdato")),
        "politiker": make_politiker(pol, "source_politikere"),
        "roller": [],
        "eierskap": [],
        "aksjeeiebok": [],
    })


def make_role(doc: Dict[str, Any]) -> Dict[str, Any]:
    return clean_doc({
        "rolleUUID": doc.get("rolleUUID"),
        "selskapRolleUUID": doc.get("selskapRolleUUID"),
        "rolle": doc.get("selskapRolle"),
        "rolleRang": doc.get("selskapRolleRang"),
        "startdato": doc.get("rolleStartdato"),
        "registrertTid": doc.get("rolleRegistrert"),
        "oppdatertTid": doc.get("rolleOppdatert"),
        "selskap": {
            "uuid": doc.get("selskapUUID"),
            "orgNr": doc.get("selskapOrgNr"),
            "navn": doc.get("selskapNavn"),
            "registrertTid": doc.get("selskapRegistrert"),
            "oppdatertTid": doc.get("selskapOppdatert"),
        },
    })


def make_company_role(doc: Dict[str, Any], politiker_lookup: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    return clean_doc({
        "rolleUUID": doc.get("rolleUUID"),
        "selskapRolleUUID": doc.get("selskapRolleUUID"),
        "rolle": doc.get("selskapRolle"),
        "rolleRang": doc.get("selskapRolleRang"),
        "startdato": doc.get("rolleStartdato"),
        "registrertTid": doc.get("rolleRegistrert"),
        "oppdatertTid": doc.get("rolleOppdatert"),
        "person": {
            "uuid": doc.get("uuid"),
            "navn": doc.get("navn"),
            "fødselsdato": doc.get("fødselsdato"),
            "fødselsår": doc.get("fødselsår"),
            "kjønn": doc.get("kjønn"),
            "politiker": match_politiker_by_name(doc.get("navn"), politiker_lookup, doc.get("fødselsår")),
        },
    })


def make_aksjeeiebok_record(doc: Dict[str, Any], politiker_lookup: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    return clean_doc({
        "år": doc.get("år"),
        "aksjeklasse": doc.get("aksjeklasse"),
        "aksjonær": {
            "navn": doc.get("aksjonærNavn"),
            "fødselsår": doc.get("fødselsår"),
            "landkode": doc.get("landkode"),
            "poststed": doc.get("postnr/sted"),
            "politiker": match_politiker_by_name(doc.get("aksjonærNavn"), politiker_lookup, doc.get("fødselsår")),
        },
        "aksjer": {
            "antall": doc.get("antallAksjer"),
            "antallTotaltISelskap": doc.get("antallAksjerSelskap"),
        },
    })


def make_person_aksjeeiebok_summary(doc: Dict[str, Any]) -> Dict[str, Any]:
    return clean_doc({
        "år": doc.get("år"),
        "aksjeklasse": doc.get("aksjeklasse"),
        "selskap": {
            "orgNr": doc.get("orgNr"),
            "navn": doc.get("selskap"),
        },
        "aksjer": {
            "antall": doc.get("antallAksjer"),
            "antallTotaltISelskap": doc.get("antallAksjerSelskap"),
        },
        "match": {
            "type": "aksjonærNavn_personNavn",
            "confidence": "medium",
            "note": "Shareholder linked to person/politician by name, not by shared unique identifier.",
        },
    })


def make_eierskap_record(doc: Dict[str, Any], politiker_lookup: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    eier_type = "person" if not is_missing(doc.get("eierPersonNavn")) or not is_missing(doc.get("eierPersonUUID")) else "selskap"
    eier = {"type": eier_type, "aksjonærNavn": doc.get("eierskapAksjonær")}

    if eier_type == "person":
        eier.update({
            "uuid": doc.get("eierPersonUUID"),
            "navn": doc.get("eierPersonNavn"),
            "fødselsdato": doc.get("eierPersonFødselsdato"),
            "fødselsår": doc.get("eierPersonFødselsår"),
            "kjønn": doc.get("eierPersonKjønn"),
            "kommune": doc.get("eierPersonKommune"),
            "kommuneNr": doc.get("eierPersonKommuneNr"),
            "poststed": doc.get("eierPersonPoststed"),
            "postnummer": doc.get("eierPersonPostkode"),
            "politiker": match_politiker_by_name(doc.get("eierPersonNavn"), politiker_lookup, doc.get("eierPersonFødselsår")),
        })
    else:
        eier.update({
            "uuid": doc.get("eierSelskapUUID"),
            "orgNr": doc.get("eierSelskapOrgNr"),
            "navn": doc.get("eierSelskapNavn"),
        })

    return clean_doc({
        "uuid": doc.get("eierskapUUID"),
        "år": doc.get("eierskapår"),
        "eier": eier,
        "aksjer": {
            "andel": doc.get("eierskapAndel"),
            "antall": doc.get("eierskapAntall"),
            "totalAntall": doc.get("eierskapTotalAntall"),
        },
        "stemmer": {
            "andel": doc.get("eierskapStemmeandel"),
            "antall": doc.get("eierskapStemmeantall"),
            "totalAntall": doc.get("eierskapTotalStemmeantall"),
        },
    })


def make_person_eierskap_summary(doc: Dict[str, Any]) -> Dict[str, Any]:
    return clean_doc({
        "uuid": doc.get("eierskapUUID"),
        "år": doc.get("eierskapår"),
        "selskap": {
            "uuid": doc.get("utstederUUID"),
            "orgNr": doc.get("utstederOrgNr"),
            "navn": doc.get("utstederNavn"),
        },
        "aksjer": {
            "andel": doc.get("eierskapAndel"),
            "antall": doc.get("eierskapAntall"),
            "totalAntall": doc.get("eierskapTotalAntall"),
        },
        "stemmer": {
            "andel": doc.get("eierskapStemmeandel"),
            "antall": doc.get("eierskapStemmeantall"),
            "totalAntall": doc.get("eierskapTotalStemmeantall"),
        },
    })


# -----------------------------------------------------------------------------
# Insert helpers
# -----------------------------------------------------------------------------

def insert_many_if_any(collection, docs: Iterable[Dict[str, Any]]) -> int:
    docs = list(docs)
    if not docs:
        return 0
    collection.insert_many(docs, ordered=False)
    return len(docs)


def safe_insert_companies(target, companies: Iterable[Dict[str, Any]], verbose: bool) -> int:
    """Insert company documents one by one so one oversized company does not stop the script."""
    written = 0
    skipped = []
    col = target["selskap"]

    for company in companies:
        # Avoid very large documents caused by huge embedded arrays.
        for array_name in ["aksjeeiebok", "eierskap", "roller"]:
            if len(company.get(array_name, [])) > MAX_COMPANY_ARRAY_ITEMS:
                skipped.append({
                    "collection": "selskap",
                    "orgNr": company.get("orgNr"),
                    "navn": company.get("navn"),
                    "reason": f"{array_name} has more than {MAX_COMPANY_ARRAY_ITEMS} embedded records",
                    "arrayLength": len(company.get(array_name, [])),
                })
                company = None
                break
        if company is None:
            continue

        try:
            col.insert_one(company)
            written += 1
        except DocumentTooLarge as exc:
            skipped.append({
                "collection": "selskap",
                "orgNr": company.get("orgNr"),
                "navn": company.get("navn"),
                "reason": "DocumentTooLarge",
                "error": str(exc),
            })
        except Exception as exc:
            skipped.append({
                "collection": "selskap",
                "orgNr": company.get("orgNr"),
                "navn": company.get("navn"),
                "reason": "InsertError",
                "error": str(exc),
            })

    if skipped:
        target["migrationLog"].insert_many(skipped)
        verbose_print(verbose, f"Skipped {len(skipped)} oversized/problematic selskap documents. See migrationLog.")

    return written


# -----------------------------------------------------------------------------
# Migration
# -----------------------------------------------------------------------------

def migrate(drop: bool = False, verbose: bool = False) -> None:
    client = MongoClient(MONGO_URI)
    source = client[SOURCE_DB]
    target = client[TARGET_DB]

    if drop:
        client.drop_database(TARGET_DB)
        verbose_print(verbose, f"Dropped existing database: {TARGET_DB}")

    verbose_print(verbose, f"Source: {SOURCE_DB} -> Target: {TARGET_DB}")

    politiker_lookup = build_politiker_lookup(source)

    # 1. Build company documents.
    companies_by_orgnr: Dict[Any, Dict[str, Any]] = {}
    for company_doc in source["selskap"].find():
        company = make_company(company_doc)
        orgnr = company.get("orgNr")
        if not is_missing(orgnr):
            companies_by_orgnr[orgnr] = company

    # 2. Build person documents from roles and embed roles in companies.
    persons: Dict[str, Dict[str, Any]] = {}
    name_to_person_key: Dict[str, str] = {}

    for role_doc in source["personer"].find():
        p_key = person_key_from_role(role_doc)
        if not p_key:
            continue

        if p_key not in persons:
            persons[p_key] = make_base_person(role_doc, politiker_lookup)
            name_key = normalize_name(role_doc.get("navn"))
            if name_key:
                name_to_person_key[name_key] = p_key

        persons[p_key]["roller"].append(make_role(role_doc))

        orgnr = role_doc.get("selskapOrgNr")
        if not is_missing(orgnr) and orgnr in companies_by_orgnr:
            companies_by_orgnr[orgnr]["roller"].append(make_company_role(role_doc, politiker_lookup))

    # 3. Add politician-only person documents when no person record exists.
    for name_key, pol_records in politiker_lookup.items():
        if name_key in name_to_person_key:
            continue
        p_key = f"politiker_navn:{name_key}"
        persons[p_key] = make_person_from_politiker(pol_records[0])
        name_to_person_key[name_key] = p_key

    # 4. Embed aksjeeiebok in companies and connect likely politician/person shareholders by name.
    for share_doc in source["aksjeeiebok"].find():
        orgnr = share_doc.get("orgNr")
        if not is_missing(orgnr) and orgnr in companies_by_orgnr:
            companies_by_orgnr[orgnr]["aksjeeiebok"].append(make_aksjeeiebok_record(share_doc, politiker_lookup))

        shareholder_key = normalize_name(share_doc.get("aksjonærNavn"))
        if shareholder_key and shareholder_key in name_to_person_key:
            persons[name_to_person_key[shareholder_key]]["aksjeeiebok"].append(make_person_aksjeeiebok_summary(share_doc))

    # 5. Embed eierskap in companies and ownership summaries in persons.
    for ownership_doc in source["eierskap"].find():
        utsteder_orgnr = ownership_doc.get("utstederOrgNr")
        if not is_missing(utsteder_orgnr) and utsteder_orgnr in companies_by_orgnr:
            companies_by_orgnr[utsteder_orgnr]["eierskap"].append(make_eierskap_record(ownership_doc, politiker_lookup))

        p_key = person_key_from_eierskap(ownership_doc)
        name_key = normalize_name(ownership_doc.get("eierPersonNavn"))

        if p_key:
            # If this person already exists by name, merge into that document instead of creating duplicate name docs.
            if name_key and name_key in name_to_person_key:
                p_key = name_to_person_key[name_key]
            elif p_key not in persons:
                persons[p_key] = make_person_from_eierskap(ownership_doc, politiker_lookup)
                if name_key:
                    name_to_person_key[name_key] = p_key

            persons[p_key]["eierskap"].append(make_person_eierskap_summary(ownership_doc))

    # 6. Write target collections. Write personer first so selskap cannot prevent it from being created.
    target["personer"].drop()
    target["selskap"].drop()
    target["migrationLog"].drop()

    personer_written = insert_many_if_any(target["personer"], persons.values())
    selskaper_written = safe_insert_companies(target, companies_by_orgnr.values(), verbose)

    # 7. Indexes.
    target["personer"].create_index([("uuid", ASCENDING)])
    target["personer"].create_index([("navn", ASCENDING)])
    target["personer"].create_index([("politiker.erPolitiker", ASCENDING)])
    target["personer"].create_index([("roller.selskap.orgNr", ASCENDING)])
    target["personer"].create_index([("eierskap.selskap.orgNr", ASCENDING)])
    target["personer"].create_index([("aksjeeiebok.selskap.orgNr", ASCENDING)])

    target["selskap"].create_index([("orgNr", ASCENDING)])
    target["selskap"].create_index([("uuid", ASCENDING)])
    target["selskap"].create_index([("navn", ASCENDING)])
    target["selskap"].create_index([("roller.person.politiker.erPolitiker", ASCENDING)])
    target["selskap"].create_index([("eierskap.eier.politiker.erPolitiker", ASCENDING)])
    target["selskap"].create_index([("aksjeeiebok.aksjonær.politiker.erPolitiker", ASCENDING)])

    target["migrationLog"].insert_one({
        "status": "complete",
        "targetDb": TARGET_DB,
        "personerWritten": personer_written,
        "selskaperWritten": selskaper_written,
        "politicianMatching": {
            "method": "normalized name, with birth year when available",
            "fields": [
                "politikere.navn -> personer.navn",
                "politikere.navn -> eierskap.eierPersonNavn",
                "politikere.navn -> aksjeeiebok.aksjonærNavn",
            ],
            "limitation": "Name-based matches are probable matches, not verified identity matches.",
        },
    })

    verbose_print(verbose, f"personer written: {personer_written}")
    verbose_print(verbose, f"selskap written: {selskaper_written}")
    verbose_print(verbose, "Migration complete.")

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create groundtruthTest with name-based politician matching")
    parser.add_argument("--drop", action="store_true", help="Drop target database before migrating")
    parser.add_argument("--verbose", action="store_true", help="Print progress to terminal")
    args = parser.parse_args()
    migrate(drop=args.drop, verbose=args.verbose)
