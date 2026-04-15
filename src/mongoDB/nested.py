# =============================================================================
# migrate_to_nested.py — Creates a nested version of the flat database.
#
# Reads from the flat database and writes transformed documents to a new
# database called "groundtruthStructured".
#
# Usage:
#   python migrate_to_nested.py
#   python migrate_to_nested.py --drop   # drop target collections before migrating
# =============================================================================

import argparse
from pymongo import MongoClient

SOURCE_DB = "groundtruth"
TARGET_DB = "groundtruthStructured"

BATCH_SIZE = 1000  # documents per insert batch


# ── Transformation functions ──────────────────────────────────────────────────

def transform_selskap(doc: dict) -> dict:
    return {
        "_id":              doc["_id"],
        "uuid":             doc.get("uuid"),
        "navn":             doc.get("navn"),
        "orgNr":            doc.get("orgNr"),
        "organisasjonstype":doc.get("organisasjonstype"),
        "naceKode":         doc.get("naceKode"),
        "datoer": {
            "etablert":     doc.get("etablertDato"),
            "oppløst":      doc.get("oppløstDato"),
        },
        "status": {
            "konkurs":      doc.get("konkursFlagg"),
            "likvidasjon":  doc.get("likvidasjonFlagg"),
        },
    }


def transform_personer(doc: dict) -> dict:
    return {
        "_id":  doc["_id"],
        "UUID": doc.get("UUID"),
        "personInfo": {
            "navn":         doc.get("navn"),
            "fødselsdato":  doc.get("fødselsdato"),
            "fødselsår":    doc.get("fødselsår"),
            "kjønnUUID":    doc.get("kjønnUUID"),
        },
        "adresse": {
            "gateadresse":  doc.get("adresse"),
            "postnummer":   doc.get("postnummer"),
            "poststed":     doc.get("poststed"),
            "kommuneNr":    doc.get("kommuneNr"),
            "kommuneNavn":  doc.get("kommuneNavn"),
            "land":         doc.get("land"),
            "landkode":     doc.get("landkode"),
        },
        "registrering": {
            "registrertTid": doc.get("registrertTid"),
            "oppdatertTid":  doc.get("oppdatertTid"),
        },
        "selskap": {
            "navn":         doc.get("selskapNavn"),
            "uuid":         doc.get("selskapUUID"),
            "orgNr":        doc.get("selskapOrgNr"),
            "registrert":   doc.get("selskapRegistrert"),
            "oppdatert":    doc.get("selskapOppdatert"),
        },
        "rolle": {
            "tittel":       doc.get("selskapRolle"),
            "uuid":         doc.get("selskapRolleUUID"),
            "rolleUUID":    doc.get("rolleUUID"),
            "rang":         doc.get("selskapRolleRang"),
            "startdato":    doc.get("rolleStartdato"),
            "sluttdato":    doc.get("rolleSluttdato"),
            "registrert":   doc.get("rolleRegistrert"),
            "oppdatert":    doc.get("rolleOppdatert"),
        },
    }


def transform_eierskap(doc: dict) -> dict:
    return {
        "_id":          doc["_id"],
        "eierskapUUID": doc.get("eierskapUUID"),
        "år":           doc.get("eierskapår"),
        "aksjonærNavn": doc.get("eierskapAksjonær"),
        "eier": {
            "person": {
                "uuid":         doc.get("eierPersonUUID"),
                "navn":         doc.get("eierPersonNavn"),
                "fødselsdato":  doc.get("eierPersonFødselsdato"),
                "fødselsår":    doc.get("eierPersonFødselsår"),
                "kjønnUUID":    doc.get("eierPersonKjønnUUID"),
                "adresse":      doc.get("eierPersonAdresse"),
                "postkode":     doc.get("eierPersonPostkode"),
                "poststed":     doc.get("eierPersonPoststed"),
                "kommuneNr":    doc.get("eierPersonKommuneNr"),
                "kommune":      doc.get("eierPersonKommune"),
            },
            "selskap": {
                "navn":         doc.get("eierSelskapNavn"),
                "uuid":         doc.get("eierSelskapUUID"),
                "orgNr":        doc.get("eierSelskapOrgNr"),
            },
        },
        "utsteder": {
            "navn":     doc.get("utstederNavn"),
            "uuid":     doc.get("utstederUUID"),
            "orgNr":    doc.get("utstederOrgNr"),
        },
        "aksjer": {
            "andel":                doc.get("eierskapAndel"),
            "antall":               doc.get("eierskapAntall"),
            "stemmeandel":          doc.get("eierskapStemmeandel"),
            "stemmeantall":         doc.get("eierskapStemmeantall"),
            "totalAntall":          doc.get("eierskapTotalAntall"),
            "totalStemmeantall":    doc.get("eierskapTotalStemmeantall"),
        },
    }


def transform_aksjeeiebok(doc: dict) -> dict:
    return {
        "_id":          doc["_id"],
        "orgNr":        doc.get("orgNr"),
        "selskap":      doc.get("selskap"),
        "år":           doc.get("år"),
        "aksjeklasse":  doc.get("aksjeklasse"),
        "aksjonær": {
            "navn":         doc.get("aksjonærNavn"),
            "fødselsår":    doc.get("fødselsår"),
            "postnr_sted":  doc.get("postnr_sted"),
            "landkode":     doc.get("landkode"),
        },
        "aksjer": {
            "antall":           doc.get("antallAksjer"),
            "antallSelskap":    doc.get("antallAksjerSelskap"),
        },
    }


def transform_politikere(doc: dict) -> dict:
    return {
        "_id": doc["_id"],
        "personInfo": {
            "navn":         doc.get("navn"),
            "fødselsdato":  doc.get("fødselsdato"),
        },
        "parti": {
            "navn":         doc.get("partinavn"),
        },
        "kommune": {
            "navn":         doc.get("kommune"),
            "nr":           doc.get("kommune_nr"),
        },
        "valg": {
            "listeplass":       doc.get("listeplass"),
            "personstemmer":    doc.get("personstemmer"),
            "stemmetillegg":    doc.get("stemmetillegg"),
            "slengere":         doc.get("slengere"),
            "endeligRangering": doc.get("endeligRangering"),
            "innvalgt":         doc.get("innvalgt"),
        },
    }


# ── Migration runner ──────────────────────────────────────────────────────────

COLLECTIONS = {
    "selskap":      transform_selskap,
    "personer":     transform_personer,
    "eierskap":     transform_eierskap,
    "aksjeeiebok":  transform_aksjeeiebok,
    "politikere":   transform_politikere,
}


def migrate(drop: bool):
    client    = MongoClient("mongodb://localhost:27017")
    source    = client[SOURCE_DB]
    target    = client[TARGET_DB]

    print(f"\n  Source: {SOURCE_DB}  →  Target: {TARGET_DB}\n")

    for col_name, transform in COLLECTIONS.items():
        src_col = source[col_name]
        tgt_col = target[col_name]

        total = src_col.count_documents({})
        if total == 0:
            print(f"  {col_name:<15} skipped (empty)")
            continue

        if drop:
            tgt_col.drop()
            print(f"  {col_name:<15} dropped existing collection")

        batch   = []
        written = 0

        for doc in src_col.find():
            batch.append(transform(doc))
            if len(batch) >= BATCH_SIZE:
                tgt_col.insert_many(batch)
                written += len(batch)
                batch = []

        if batch:
            tgt_col.insert_many(batch)
            written += len(batch)

        print(f"  {col_name:<15} {written:>7} documents written")

    print(f"\n  Migration complete.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate flat DB to nested structure")
    parser.add_argument("--drop", action="store_true", help="Drop target collections before migrating")
    args = parser.parse_args()
    migrate(args.drop)