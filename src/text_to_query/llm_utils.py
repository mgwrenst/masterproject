import json
import yaml
import re
from pathlib import Path
from openai import OpenAI
from config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)


def load_schema():
    """Load schema from YAML file."""
    # Get the path relative to this file
    # From src/text_to_query/llm_utils.py -> ../../data/schema.yaml
    schema_path = Path(__file__).parent.parent.parent / "data" / "schema.yaml"

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_data = yaml.safe_load(f)
            return yaml.dump(schema_data, allow_unicode=True)
    except FileNotFoundError:
        print(f"Error: schema.yaml was not found at {schema_path}!")
        return ""


def generate_query(user_question, custom_schema=None):
    """
    Generate a MongoDB query command from a natural language question.

    Args:
        user_question: Natural language question in Norwegian
        custom_schema: Optional custom schema (None by default, does not use benchmark descriptions)

    Returns:
        MongoDB command string (e.g., "db.collection.find({...})")
    """
    # Choose between user schema or predefined schema
    if custom_schema:
        schema = custom_schema
    else:
        schema = load_schema()

    prompt = f"""
Gitt et spørsmål, lag en enkelt syntaktisk korrekt MongoDB-kommando basert på det oppgitte skjemaet.

[Skjema]:
'{schema}'

[Regler]:
1) Bruk KUN dokument-samlinger (collections) som finnes i skjemaet
2) Bruk KUN feltnavn som er eksplisitt definert i skjemaet
3) "_id"-feltet er MongoDB's interne ObjectID - bruk IKKE dette for domenespesifikke ID-er
4) Domenespesifikke ID-er følger mønsteret: PASIENT_ID, TRANSAKSJON_ID, KRAV_ID, osv. (UUID-format)
5) Bruk enkle anførselstegn (') rundt strenger og feltnavn i MongoDB-kommandoen
6) Bruk doble krøllparenteser ({{}}) for dictionaries i kommandoen
7) Ved $group-operasjoner: vær nøye med "group key"
8) Ved find()-operasjoner: vær nøye med hvilke felt som brukes
9) Hvis spørsmålet ikke kan besvares med tilgjengelig informasjon, returner: {{"error": "Svar ikke mulig basert på oppgitt informasjon"}}

[Format]:
- Returner BARE en MongoDB-kommando som starter med "db."
- INGEN forklaringer, unnskyldninger eller ekstra tekst
- INGEN tekst før eller etter kommandoen
- INGEN JSON-objekt, bare ren MongoDB-kommando

[Eksempler]:

Spørsmål: "Hvilke organisasjonstyper finnes blant selskaper i konkurs?"
Svar: db.selskap.distinct('organisasjonstype', {{'konkursFlagg': 1}})

Spørsmål: "Finn alle typer roller som en person kan ha"
Svar: db.personer.distinct('selskapRolle')

Spørsmål: "Hvor mange selskaper er registrert i Oslo?"
Svar: db.selskap.countDocuments({{'forretningsAdresse.poststed': 'Oslo'}})

Spørsmål: "Finn alle selskaper som er registrert etter 2020"
Svar: db.selskap.find({{'registreringsDato': {{'$gte': '2020-01-01'}}}})

Spørsmål: "Finn selskapsnavn og organisasjonsnummer for alle AS-selskaper"
Svar: db.selskap.find({{'organisasjonstype': 'AS'}}, {{'selskapNavn': 1, 'organisasjonsnummer': 1, '_id': 0}})

---

[Q]: '{user_question}'
[MongoDB]: 
"""

    try:
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {
                    "role": "system",
                    "content": "Du er en ekspert på MongoDB-spørringer. Du svarer BARE med gyldige MongoDB-kommandoer som starter med 'db.' uten noen ekstra tekst, forklaringer eller markdown-formatering."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
        )

        generated_query = response.choices[0].message.content.strip()

        # Remove markdown code blocks if present
        generated_query = re.sub(r'^```(?:javascript|js|mongodb|json)?\s*\n?', '', generated_query)
        generated_query = re.sub(r'\n?```\s*$', '', generated_query)
        generated_query = generated_query.strip()

        # Validate that it starts with "db." or is an error response
        if not generated_query.startswith("db."):
            # Check if it's an error response in JSON format
            try:
                error_obj = json.loads(generated_query)
                if "error" in error_obj:
                    return generated_query  # Return error as JSON string
            except json.JSONDecodeError:
                pass

            # If we get here, it's an invalid response
            raise ValueError(f"Generated query does not start with 'db.': {generated_query}")

        return generated_query

    except Exception as e:
        print(f"Error generating query: {e}")
        # Return error in JSON format for consistency
        return json.dumps({"error": f"Kunne ikke generere spørring: {str(e)}"}, ensure_ascii=False)