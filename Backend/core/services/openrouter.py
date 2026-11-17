import os

from openai import OpenAI

EMBEDDING_MODEL = "nvidia/nemotron-3.5-embed-8b:free"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def create_embeddings(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPEN_ROUTER_KEY")
    if not api_key:
        raise RuntimeError("Set OPENROUTER_API_KEY to create knowledge-base embeddings.")

    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
    response = client.embeddings.create(
        model=os.getenv("EMBEDDING_MODEL", EMBEDDING_MODEL),
        input=texts,
    )
    return [item.embedding for item in response.data]
