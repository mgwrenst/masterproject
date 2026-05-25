"""Create a lossless hybrid structured MongoDB database from the flat database.

The target keeps all source records in queryable collections, while also
building structured company/person documents with useful embedded summaries.
Large unbounded relationships are not allowed to make company documents fail.
"""

import argparse
import math
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, Optional

from pymongo import ASCENDING, MongoClient

SOURCE_DB = "groundtruth"
TARGET_DB = "groundtruthStructured"
MONGO_URI = "mongodb://localhost:27017"
MAX_EMBEDDED_ITEMS = 100


def is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def clean_value(value: Any) -> Any:
    if isinstance(value, dict):
        return clean_doc(value)
    if isinstance(value, list):
        return [clean_value(item) for item in value]
    return value


def clean_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {key: clean_value(value) for key, value in doc.items()}


def normalize_name(value: Any) -> Optional[str]:
    if is_missing(value):
        return None
    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text or None


def birth_year_from_date(value: Any) -> Optional[int]:
    if is_missing(value):
        return None
    match = re.search(r"(\d{4})", str(value))
    return int(match.group(1)) if match else None


def safe_int(value: Any) -> Optional[int]:
    if is_missing(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def insert_many(collection, docs: Iterable[Dict[str, Any]]) -> int:
    docs = list(docs)
    if not docs:
        return 0
    result = collection.insert_many(docs, ordered=False)
    return len(result.inserted_ids)


def copy_collection(source, target, source_name: str, target_name: str | None = None) -> int:
    target_name = target_name or source_name
    docs = [clean_doc(doc) for doc in source[source_name].find()]
    target[target_name].drop()
    return insert_many(target[target_name], docs)


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


def build_politiker_lookup(source) -> Dict[str, list[Dict[str, Any]]]:
    lookup: Dict[str, list[Dict[str, Any]]] = {}
    for doc in source["politikere"].find():
        key = normalize_name(doc.get("navn"))
        if key:
            lookup.setdefault(key, []).append(doc)
    return lookup


def match_politiker_by_name(
    name: Any,
    politiker_lookup: Dict[str, list[Dict[str, Any]]],
    birth_year: Any = None,
) -> Dict[str, Any]:
    key = normalize_name(name)
    if not key or key not in politiker_lookup:
        return {"erPolitiker": False}

    candidates = politiker_lookup[key]
    input_year = safe_int(birth_year)
    if input_year is not None:
        for candidate in candidates:
            if birth_year_from_date(candidate.get("fødselsdato")) == input_year:
                return create_politician_match(candidate, "navn_fødselsår")

    result = create_politician_match(candidates[0], "navn")
    if len(candidates) > 1:
        result["match"]["ambiguousCandidates"] = len(candidates)
    return result


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
        "relasjoner": {
            "antallRoller": 0,
            "antallEierskap": 0,
            "antallAksjeeierbok": 0,
            "harRoller": False,
            "harEierskap": False,
            "harAksjeeierbok": False,
            "embeddedLimit": MAX_EMBEDDED_ITEMS,
        },
        "roller": [],
        "eierskap": [],
        "aksjeeiebok": [],
    })


def create_company_role(doc: Dict[str, Any], politiker_lookup: Dict[str, list[Dict[str, Any]]]) -> Dict[str, Any]:
    return clean_doc({
        "rolleUUID": doc.get("rolleUUID"),
        "selskapRolleUUID": doc.get("selskapRolleUUID"),
        "rolle": doc.get("selskapRolle"),
        "rolleRang": doc.get("selskapRolleRang"),
        "startdato": doc.get("rolleStartdato"),
        "sluttdato": doc.get("rolleSluttdato"),
        "person": {
            "uuid": doc.get("uuid"),
            "navn": doc.get("navn"),
            "fødselsdato": doc.get("fødselsdato"),
            "fødselsår": doc.get("fødselsår"),
            "kjønn": doc.get("kjønn"),
            "politiker": match_politiker_by_name(doc.get("navn"), politiker_lookup, doc.get("fødselsår")),
        },
    })


def create_company_ownership(doc: Dict[str, Any], politiker_lookup: Dict[str, list[Dict[str, Any]]]) -> Dict[str, Any]:
    owner_type = "person" if not is_missing(doc.get("eierPersonNavn")) or not is_missing(doc.get("eierPersonUUID")) else "selskap"
    owner = {"type": owner_type, "aksjonærNavn": doc.get("eierskapAksjonær")}
    if owner_type == "person":
        owner.update({
            "uuid": doc.get("eierPersonUUID"),
            "navn": doc.get("eierPersonNavn"),
            "fødselsdato": doc.get("eierPersonFødselsdato"),
            "fødselsår": doc.get("eierPersonFødselsår"),
            "politiker": match_politiker_by_name(doc.get("eierPersonNavn"), politiker_lookup, doc.get("eierPersonFødselsår")),
        })
    else:
        owner.update({
            "uuid": doc.get("eierSelskapUUID"),
            "orgNr": doc.get("eierSelskapOrgNr"),
            "navn": doc.get("eierSelskapNavn"),
        })

    return clean_doc({
        "uuid": doc.get("eierskapUUID"),
        "år": doc.get("eierskapår"),
        "eier": owner,
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


def create_company_shareholder(doc: Dict[str, Any], politiker_lookup: Dict[str, list[Dict[str, Any]]]) -> Dict[str, Any]:
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


def person_key(name: Any, uuid: Any = None, prefix: str = "person") -> Optional[str]:
    if not is_missing(uuid):
        return f"uuid:{uuid}"
    name_key = normalize_name(name)
    if name_key:
        return f"{prefix}:{name_key}"
    return None


def ensure_person(persons: Dict[str, Dict[str, Any]], key: str, base: Dict[str, Any]) -> Dict[str, Any]:
    if key not in persons:
        persons[key] = clean_doc({
            **base,
            "roller": [],
            "eierskap": [],
            "aksjeeiebok": [],
            "relasjoner": {
                "antallRoller": 0,
                "antallEierskap": 0,
                "antallAksjeeierbok": 0,
                "embeddedLimit": MAX_EMBEDDED_ITEMS,
            },
        })
    return persons[key]


def build_structured_companies(source, politiker_lookup) -> tuple[list[Dict[str, Any]], Dict[Any, list[Dict[str, Any]]]]:
    companies = []
    companies_by_orgnr: Dict[Any, list[Dict[str, Any]]] = defaultdict(list)
    for doc in source["selskap"].find():
        company = create_company(doc)
        companies.append(company)
        if not is_missing(company.get("orgNr")):
            companies_by_orgnr[company["orgNr"]].append(company)

    for role in source["personer"].find():
        for company in companies_by_orgnr.get(role.get("selskapOrgNr"), []):
            company["relasjoner"]["antallRoller"] += 1
            company["relasjoner"]["harRoller"] = True
            if len(company["roller"]) < MAX_EMBEDDED_ITEMS:
                company["roller"].append(create_company_role(role, politiker_lookup))

    for ownership in source["eierskap"].find():
        for company in companies_by_orgnr.get(ownership.get("utstederOrgNr"), []):
            company["relasjoner"]["antallEierskap"] += 1
            company["relasjoner"]["harEierskap"] = True
            if len(company["eierskap"]) < MAX_EMBEDDED_ITEMS:
                company["eierskap"].append(create_company_ownership(ownership, politiker_lookup))

    for shareholder in source["aksjeeiebok"].find():
        for company in companies_by_orgnr.get(shareholder.get("orgNr"), []):
            company["relasjoner"]["antallAksjeeierbok"] += 1
            company["relasjoner"]["harAksjeeierbok"] = True
            if len(company["aksjeeiebok"]) < MAX_EMBEDDED_ITEMS:
                company["aksjeeiebok"].append(create_company_shareholder(shareholder, politiker_lookup))

    return companies, companies_by_orgnr


def build_structured_persons(source, politiker_lookup) -> list[Dict[str, Any]]:
    persons: Dict[str, Dict[str, Any]] = {}
    name_to_key: Dict[str, str] = {}

    for role in source["personer"].find():
        key = person_key(role.get("navn"), role.get("uuid")) or person_key(role.get("navn"), prefix="rolle_navn")
        if not key:
            continue
        name_key = normalize_name(role.get("navn"))
        if name_key:
            name_to_key.setdefault(name_key, key)
        person = ensure_person(persons, key, {
            "uuid": role.get("uuid"),
            "navn": role.get("navn"),
            "fødselsdato": role.get("fødselsdato"),
            "fødselsår": role.get("fødselsår"),
            "kjønn": role.get("kjønn"),
            "politiker": match_politiker_by_name(role.get("navn"), politiker_lookup, role.get("fødselsår")),
        })
        person["relasjoner"]["antallRoller"] += 1
        if len(person["roller"]) < MAX_EMBEDDED_ITEMS:
            person["roller"].append(clean_doc({
                "rolle": role.get("selskapRolle"),
                "selskap": {
                    "uuid": role.get("selskapUUID"),
                    "orgNr": role.get("selskapOrgNr"),
                    "navn": role.get("selskapNavn"),
                },
            }))

    for name_key, records in politiker_lookup.items():
        if name_key in name_to_key:
            continue
        pol = records[0]
        key = f"politiker:{name_key}"
        name_to_key[name_key] = key
        ensure_person(persons, key, {
            "navn": pol.get("navn"),
            "fødselsdato": pol.get("fødselsdato"),
            "fødselsår": birth_year_from_date(pol.get("fødselsdato")),
            "politiker": create_politician_match(pol, "source_politikere"),
        })

    for ownership in source["eierskap"].find():
        key = person_key(ownership.get("eierPersonNavn"), ownership.get("eierPersonUUID"))
        name_key = normalize_name(ownership.get("eierPersonNavn"))
        if name_key and name_key in name_to_key:
            key = name_to_key[name_key]
        if not key:
            continue
        if name_key:
            name_to_key.setdefault(name_key, key)
        person = ensure_person(persons, key, {
            "uuid": ownership.get("eierPersonUUID"),
            "navn": ownership.get("eierPersonNavn"),
            "fødselsdato": ownership.get("eierPersonFødselsdato"),
            "fødselsår": ownership.get("eierPersonFødselsår"),
            "kjønn": ownership.get("eierPersonKjønn"),
            "politiker": match_politiker_by_name(ownership.get("eierPersonNavn"), politiker_lookup, ownership.get("eierPersonFødselsår")),
        })
        person["relasjoner"]["antallEierskap"] += 1
        if len(person["eierskap"]) < MAX_EMBEDDED_ITEMS:
            person["eierskap"].append(clean_doc({
                "uuid": ownership.get("eierskapUUID"),
                "år": ownership.get("eierskapår"),
                "selskap": {
                    "uuid": ownership.get("utstederUUID"),
                    "orgNr": ownership.get("utstederOrgNr"),
                    "navn": ownership.get("utstederNavn"),
                },
                "aksjer": {
                    "andel": ownership.get("eierskapAndel"),
                    "antall": ownership.get("eierskapAntall"),
                },
            }))

    for shareholder in source["aksjeeiebok"].find():
        name_key = normalize_name(shareholder.get("aksjonærNavn"))
        if not name_key or name_key not in name_to_key:
            continue
        person = persons[name_to_key[name_key]]
        person["relasjoner"]["antallAksjeeierbok"] += 1
        if len(person["aksjeeiebok"]) < MAX_EMBEDDED_ITEMS:
            person["aksjeeiebok"].append(clean_doc({
                "år": shareholder.get("år"),
                "aksjeklasse": shareholder.get("aksjeklasse"),
                "selskap": {
                    "orgNr": shareholder.get("orgNr"),
                    "navn": shareholder.get("selskap"),
                },
                "aksjer": {
                    "antall": shareholder.get("antallAksjer"),
                    "antallTotaltISelskap": shareholder.get("antallAksjerSelskap"),
                },
            }))

    return list(persons.values())


def create_indexes(target) -> None:
    target["selskap"].create_index([("orgNr", ASCENDING)])
    target["selskap"].create_index([("navn", ASCENDING)])
    target["selskap"].create_index([("status.konkursFlagg", ASCENDING)])
    target["selskap"].create_index([("status.likvidasjonFlagg", ASCENDING)])
    target["selskap"].create_index([("bransje.naceBeskrivelse", ASCENDING)])
    target["selskap"].create_index([("relasjoner.harRoller", ASCENDING)])
    target["selskap"].create_index([("relasjoner.harEierskap", ASCENDING)])
    target["selskap"].create_index([("relasjoner.harAksjeeierbok", ASCENDING)])

    target["personer"].create_index([("uuid", ASCENDING)])
    target["personer"].create_index([("navn", ASCENDING)])
    target["personer"].create_index([("politiker.erPolitiker", ASCENDING)])
    target["personer"].create_index([("roller.selskap.orgNr", ASCENDING)])
    target["personer"].create_index([("eierskap.selskap.orgNr", ASCENDING)])

    target["roller"].create_index([("selskapOrgNr", ASCENDING)])
    target["roller"].create_index([("navn", ASCENDING)])
    target["roller"].create_index([("fødselsdato", ASCENDING)])
    target["roller"].create_index([("selskapRolle", ASCENDING)])

    target["politikere"].create_index([("navn", ASCENDING)])
    target["politikere"].create_index([("fødselsdato", ASCENDING)])
    target["politikere"].create_index([("partinavn", ASCENDING)])
    target["politikere"].create_index([("innvalgt", ASCENDING)])

    target["eierskap"].create_index([("utstederOrgNr", ASCENDING)])
    target["eierskap"].create_index([("eierPersonNavn", ASCENDING)])
    target["eierskap"].create_index([("eierPersonFødselsdato", ASCENDING)])
    target["eierskap"].create_index([("eierskapår", ASCENDING)])

    target["aksjeeiebok"].create_index([("orgNr", ASCENDING)])
    target["aksjeeiebok"].create_index([("år", ASCENDING)])
    target["aksjeeiebok"].create_index([("aksjonærNavn", ASCENDING)])
    target["aksjeeiebok"].create_index([("aksjeklasse", ASCENDING)])


def create_structured_database(drop: bool = False) -> None:
    client = MongoClient(MONGO_URI)
    source = client[SOURCE_DB]
    target = client[TARGET_DB]

    if drop:
        client.drop_database(TARGET_DB)

    target["migrationLog"].drop()
    politiker_lookup = build_politiker_lookup(source)

    copied_counts = {
        "roller": copy_collection(source, target, "personer", "roller"),
        "politikere": copy_collection(source, target, "politikere"),
        "eierskap": copy_collection(source, target, "eierskap"),
        "aksjeeiebok": copy_collection(source, target, "aksjeeiebok"),
    }

    target["selskap"].drop()
    target["personer"].drop()
    structured_companies, _ = build_structured_companies(source, politiker_lookup)
    structured_persons = build_structured_persons(source, politiker_lookup)
    company_count = insert_many(target["selskap"], structured_companies)
    person_count = insert_many(target["personer"], structured_persons)

    create_indexes(target)

    truncated = defaultdict(int)
    for company in structured_companies:
        for name in ["roller", "eierskap", "aksjeeiebok"]:
            count_name = {
                "roller": "antallRoller",
                "eierskap": "antallEierskap",
                "aksjeeiebok": "antallAksjeeierbok",
            }[name]
            if company["relasjoner"][count_name] > len(company[name]):
                truncated[f"selskap.{name}"] += 1

    target["migrationLog"].insert_one({
        "status": "complete",
        "targetDb": TARGET_DB,
        "sourceDb": SOURCE_DB,
        "model": "hybrid_structured_lossless",
        "allSourceRowsPreserved": True,
        "copiedCollections": copied_counts,
        "structuredCollections": {
            "selskap": company_count,
            "personer": person_count,
        },
        "embeddedLimitPerArray": MAX_EMBEDDED_ITEMS,
        "truncatedEmbeddedArrays": dict(truncated),
        "note": (
            "Full rows are preserved in roller, politikere, eierskap and aksjeeiebok. "
            "Selskap/personer contain structured embedded summaries for common navigation."
        ),
    })

    print(f"Created '{TARGET_DB}' from '{SOURCE_DB}' as a lossless hybrid structured database.")
    print(f"  selskap: {company_count:,}")
    print(f"  personer: {person_count:,}")
    for name, count in copied_counts.items():
        print(f"  {name}: {count:,}")
    if truncated:
        print(f"  embedded arrays truncated for summaries: {dict(truncated)}")

    client.close()


def migrate(drop: bool = False) -> None:
    create_structured_database(drop=drop)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create the structured groundtruth MongoDB database")
    parser.add_argument("--drop", action="store_true", help="Drop target database before migrating")
    args = parser.parse_args()
    create_structured_database(drop=args.drop)
