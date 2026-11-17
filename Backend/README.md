# Backend

Install dependencies and configure a provider key:

```powershell
uv sync
Copy-Item .env.example .env
```

Set `GROQ_API_KEY` in `.env` to run the default chat supervisor. Set
`OPENROUTER_API_KEY` to use knowledge-base embeddings.

Run the API from this directory:

```powershell
uv run fastapi dev
```

Run the offline backend tests:

```powershell
uv run python -m unittest discover -s tests -t .
```
