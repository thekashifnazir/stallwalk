# Voice agent

An ElevenLabs Conversational AI agent called "stallwalk". Shoppers ask what's on the stalls, and a kitchen manager asks what's run out or what an order would cost. It answers only from the app, through five read-only webhook tools:

| Tool | Endpoint | Query |
|---|---|---|
| find_item | GET /api/agent/find | q |
| list_stalls | GET /api/agent/stalls | |
| whats_run_out | GET /api/agent/restock | |
| split_order | GET /api/agent/order | order |
| web_find | GET /api/agent/web_find | items |

Each endpoint answers `{"answer": "..."}`. The prompt makes the agent use a tool before any stock, price, restock or order answer. It never says a price that isn't in a tool answer, and it says "web estimate" when the tool does. Answers stay under three sentences.

## Set up or re-point

```
uv run python voice/setup_agent.py --public-url https://<tunnel>.trycloudflare.com
uv run python voice/setup_agent.py --public-url https://<tunnel>.trycloudflare.com --test
```

- ELEVENLABS_API_KEY is read from stallwalk/.env.
- Quick tunnel URLs change. Re-run with the new URL and the four tools are updated in place.
- voice/agent.json holds ids only (agent, tools, tests, last public URL). There are no secrets in it. The app reads it at GET /api/agent/id to show the widget.
- `--test` runs two text-only ElevenLabs agent tests: a price question must go through a tool, and the agent mustn't invent a saffron price when told not to check. A test reply that calls a tool hits the real (read-only) endpoint.
- `--fresh` ignores agent.json and creates a new agent and tools.

Pattern taken from the Dwelly voice agent's setup script (greatagent-voice/voice/setup_agent.py).
