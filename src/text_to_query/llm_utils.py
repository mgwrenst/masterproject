import json
import yaml
from pathlib import Path
from openai import OpenAI
from config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)


def load_schema():
    """Load schema from YAML file."""
    # Get the path relative to this file
    # From src/text_to_query/llm_utils.py -> ../../data/schema.yaml
    schema_path = Path(__file__).parent.parent.parent / "data" / "schema_test.yaml"

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_data = yaml.safe_load(f)
            return yaml.dump(schema_data, allow_unicode=True)
    except FileNotFoundError:
        print(f"Error: schema.yaml was not found at {schema_path}!")
        return ""


def generate_query(user_question, custom_schema=None):
    # Choose between user schema or predefined schema
    if custom_schema:
        schema = custom_schema
    else:
        schema = load_schema()

    prompt = f"""
    Gitt et spørsmål, lag en enkelt syntaktisk korrekt MongoDB-spørring basert på det oppgitte skjemaet og merknadede.
    Bare spør etter relevante felt basert på spørsmålet. Vær nøye med å kun bruke feltnavnene som er synlige i skjemabeskrivelsen.
    Pass på at du ikke spør etter felt som ikke eksisterer.

    [Skjema]:
    '{schema}'

    [Merknader]:
    1) Bruk kun de dokument-samlingene (collections) som er oppgitt i skjemaet.
    2) Bruk feltnavnene som er eksplisitt nevnt eller implisert i spørsmålet.
    3) Ikke inkluder forklaringer eller unnskyldninger i svaret ditt. Lever resultatet som et gyldig JSON-objekt.
    4) Hvis spørsmålet ikke kan besvares med informasjonen som er gitt, svar med: {{"error": "Svar ikke mulig basert på oppgitt informasjon"}}
    5) Vær nøye med "group key" som brukes for $group-operatoren når det er nødvendig.
    6) Vær nøye med hvilke felt som brukes i find()-operatoren.
    7) Husk å bruke anførselstegn der det er nødvendig, for eksempel rundt strenger.
    8) "_id"-feltet brukes kun som intern MongoDB ObjectID og ikke som den domenespesifikke ID-en for objektene. Objektene identifiseres med en UUID i felt som følger strukturen PASIENT_ID, TRANSAKSJON_ID, KRAV_ID, osv.
    9) Returner BARE et JSON-objekt, uten ekstra tekst før eller etter.

    [Q] = Spørsmål, [MongoDB] = Svar (korrekt spørring som JSON-objekt)

    Basert på informasjonen over, generer en MongoDB-spørring for følgende spørsmål:
    [Q]: '{user_question}'
    [MongoDB]: 

    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )

    response_text = response.choices[0].message.content.strip()

    # Remove markdown code blocks if present
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        # Remove first and last lines (the ``` markers)
        response_text = "\n".join(lines[1:-1])
        # Remove language identifier if present (e.g., ```json)
        if lines[0].startswith("```"):
            response_text = "\n".join(lines[1:-1])

    # Remove any leading/trailing whitespace
    response_text = response_text.strip()

    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
        print(f"Response was: {response_text}")
        raise