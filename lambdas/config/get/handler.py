from db import api_response
from config import load_config


def handler(event, context):
    # config.json holds fee rates and targets only (no secrets) — the Streamlit app reads it
    # to populate platform lists and run what-if pricing with the same formulas as the backend.
    return api_response(200, load_config())
