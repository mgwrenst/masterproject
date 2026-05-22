"""Create the structured MongoDB database from the flat groundtruth database."""

import argparse
import math
import re
from typing import Any, Dict, Iterable, List, Optional

from pymongo import ASCENDING, MongoClient
from pymongo.errors import DocumentTooLarge

SOURCE_DB = "groundtruth"
TARGET_DB = "groundtruthStructured"
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


def create_politician_match(doc: Dict[str, Any], match_type: str) -> Dict[str, Any]:
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
                return create_politician_match(candidate, "navn_fødselsår")

    # Name-only fallback. This is useful for your experiment, but less certain.
    pol = candidates[0]
    result = create_politician_match(pol, "navn")
    if len(candidates) > 1:
        result["match"]["ambiguousCandidates"] = len(candidates)
        result["match"]["note"] = "Multiple politicians had the same normalized name. First candidate was used."
    return result


# -----------------------------------------------------------------------------
# Document builders
# -----------------------------------------------------------------------------

def create_company(doc: Dict[str, Any]) -> Dict[str, Any]:
    return clean_doc({
        "_id": doc.get("_id"),
        "uuid": doc.get("uuid"),
        "orgNr": doc.get("orgNr"),
        "navn": doc.get("navn"),
        "organisasjonstype": doc.get("organisasjonstype"),
        "bransje": {
            "naceKode": doc.get("naceKode"),
            "naceBeskrivelse": doc.get("naceBeskrivelse"),
        },
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


def create_person_from_role(doc: Dict[str, Any], politiker_lookup: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
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


def create_person_from_ownership(doc: Dict[str, Any], politiker_lookup: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
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


def create_person_from_politician(pol: Dict[str, Any]) -> Dict[str, Any]:
    return clean_doc({
        "navn": pol.get("navn"),
        "fødselsdato": pol.get("fødselsdato"),
        "fødselsår": birth_year_from_date(pol.get("fødselsdato")),
        "politiker": create_politician_match(pol, "source_politikere"),
        "roller": [],
        "eierskap": [],
        "aksjeeiebok": [],
    })


def create_person_role(doc: Dict[str, Any]) -> Dict[str, Any]:
    return clean_doc({
        "rolleUUID": doc.get("rolleUUID"),
        "selskapRolleUUID": doc.get("selskapRolleUUID"),
        "rolle": doc.get("selskapRolle"),
        "rolleRang": doc.get("selskapRolleRang"),
        "startdato": doc.get("rolleStartdato"),
        "sluttdato": doc.get("rolleSluttdato"),
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


def create_company_role(doc: Dict[str, Any], politiker_lookup: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    return clean_doc({
        "rolleUUID": doc.get("rolleUUID"),
        "selskapRolleUUID": doc.get("selskapRolleUUID"),
        "rolle": doc.get("selskapRolle"),
        "rolleRang": doc.get("selskapRolleRang"),
        "startdato": doc.get("rolleStartdato"),
        "sluttdato": doc.get("rolleSluttdato"),
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


def create_shareholder_record(doc: Dict[str, Any], politiker_lookup: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
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


def create_person_share_summary(doc: Dict[str, Any]) -> Dict[str, Any]:
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


def create_ownership_record(doc: Dict[str, Any], politiker_lookup: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
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


def create_person_ownership_summary(doc: Dict[str, Any]) -> Dict[str, Any]:
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

def insert_documents(collection, docs: Iterable[Dict[str, Any]]) -> int:
    docs = list(docs)
    if not docs:
        return 0
    collection.insert_many(docs, ordered=False)
    return len(docs)


def insert_company_documents(target, companies: Iterable[Dict[str, Any]]) -> tuple[int, int]:
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

    return written, len(skipped)


# -----------------------------------------------------------------------------
# Migration
# -----------------------------------------------------------------------------

def create_structured_database(drop: bool = False) -> None:
    client = MongoClient(MONGO_URI)
    source = client[SOURCE_DB]
    target = client[TARGET_DB]

    if drop:
        client.drop_database(TARGET_DB)

    politiker_lookup = build_politiker_lookup(source)

    # 1. Build company documents.
    companies_by_orgnr: Dict[Any, Dict[str, Any]] = {}
    for company_doc in source["selskap"].find():
        company = create_company(company_doc)
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
            persons[p_key] = create_person_from_role(role_doc, politiker_lookup)
            name_key = normalize_name(role_doc.get("navn"))
            if name_key:
                name_to_person_key[name_key] = p_key

        persons[p_key]["roller"].append(create_person_role(role_doc))

        orgnr = role_doc.get("selskapOrgNr")
        if not is_missing(orgnr) and orgnr in companies_by_orgnr:
            companies_by_orgnr[orgnr]["roller"].append(create_company_role(role_doc, politiker_lookup))

    # 3. Add politician-only person documents when no person record exists.
    for name_key, pol_records in politiker_lookup.items():
        if name_key in name_to_person_key:
            continue
        p_key = f"politiker_navn:{name_key}"
        persons[p_key] = create_person_from_politician(pol_records[0])
        name_to_person_key[name_key] = p_key

    # 4. Embed aksjeeiebok in companies and connect likely politician/person shareholders by name.
    for share_doc in source["aksjeeiebok"].find():
        orgnr = share_doc.get("orgNr")
        if not is_missing(orgnr) and orgnr in companies_by_orgnr:
            companies_by_orgnr[orgnr]["aksjeeiebok"].append(create_shareholder_record(share_doc, politiker_lookup))

        shareholder_key = normalize_name(share_doc.get("aksjonærNavn"))
        if shareholder_key and shareholder_key in name_to_person_key:
            persons[name_to_person_key[shareholder_key]]["aksjeeiebok"].append(create_person_share_summary(share_doc))

    # 5. Embed eierskap in companies and ownership summaries in persons.
    for ownership_doc in source["eierskap"].find():
        utsteder_orgnr = ownership_doc.get("utstederOrgNr")
        if not is_missing(utsteder_orgnr) and utsteder_orgnr in companies_by_orgnr:
            companies_by_orgnr[utsteder_orgnr]["eierskap"].append(create_ownership_record(ownership_doc, politiker_lookup))

        p_key = person_key_from_eierskap(ownership_doc)
        name_key = normalize_name(ownership_doc.get("eierPersonNavn"))

        if p_key:
            # If this person already exists by name, merge into that document instead of creating duplicate name docs.
            if name_key and name_key in name_to_person_key:
                p_key = name_to_person_key[name_key]
            elif p_key not in persons:
                persons[p_key] = create_person_from_ownership(ownership_doc, politiker_lookup)
                if name_key:
                    name_to_person_key[name_key] = p_key

            persons[p_key]["eierskap"].append(create_person_ownership_summary(ownership_doc))

    # 6. Write target collections. Write personer first so selskap cannot prevent it from being created.
    target["personer"].drop()
    target["selskap"].drop()
    target["migrationLog"].drop()

    personer_written = insert_documents(target["personer"], persons.values())
    selskaper_written, skipped_selskaper = insert_company_documents(target, companies_by_orgnr.values())

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
    target["selskap"].create_index([("bransje.naceKode", ASCENDING)])
    target["selskap"].create_index([("roller.person.politiker.erPolitiker", ASCENDING)])
    target["selskap"].create_index([("eierskap.eier.politiker.erPolitiker", ASCENDING)])
    target["selskap"].create_index([("aksjeeiebok.aksjonær.politiker.erPolitiker", ASCENDING)])

    target["migrationLog"].insert_one({
        "status": "complete",
        "targetDb": TARGET_DB,
        "personerWritten": personer_written,
        "selskaperWritten": selskaper_written,
        "selskaperSkipped": skipped_selskaper,
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

    print(f"Created '{TARGET_DB}' from '{SOURCE_DB}'.")
    print(f"  personer: {personer_written:,}")
    print(f"  selskap: {selskaper_written:,}")
    if skipped_selskaper:
        print(f"  skipped selskap: {skipped_selskaper:,} (see migrationLog)")

    client.close()


def migrate(drop: bool = False) -> None:
    create_structured_database(drop=drop)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create the structured groundtruth MongoDB database")
    parser.add_argument("--drop", action="store_true", help="Drop target database before migrating")
    args = parser.parse_args()
    create_structured_database(drop=args.drop)
