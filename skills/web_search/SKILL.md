# web_search

Search the web with DuckDuckGo and return the top results.

- **Category:** `deep_web_search`
- **Permissions:** `network` (read-only; no approval required)
- **Input:** `{ "query": "<text>", "max_results": 5 }`
- **Output:** `{ "query": "<text>", "results": [ { "title", "url", "snippet" } ] }`

Run it via the gateway:

```bash
curl -s -X POST http://localhost:8000/skills/run \
  -H "Authorization: Bearer operator-dev-token" -H 'Content-Type: application/json' \
  -d '{"name":"web_search","version":"1.0.0","arguments":{"query":"metis memory engine","max_results":5}}'
```

The query is supplied by the trusted caller; retrieved/untrusted content never drives it. Implemented
with the `ddgs` package; a blocked or flaky search returns an empty `results` list rather than failing.
