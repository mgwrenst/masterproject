import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME")

if not OPENAI_API_KEY:
    raise ValueError("No OpenAI API key provided!")