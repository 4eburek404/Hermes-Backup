# hh.ru request examples

These examples are kept outside `SKILL.md` so the skill core stays procedural.
Always include a non-empty `User-Agent`; hh.ru rejects unset/blacklisted agents.

## cURL examples

```bash
# Search vacancies
curl -s 'https://api.hh.ru/vacancies?text=Python&area=1&per_page=10' \
  -H 'Accept: application/json' \
  -H 'User-Agent: Hermes/1.0'

# Vacancy detail
curl -s 'https://api.hh.ru/vacancies/12345678' \
  -H 'Accept: application/json' \
  -H 'User-Agent: Hermes/1.0'

# Employer info
curl -s 'https://api.hh.ru/employers/12345' \
  -H 'Accept: application/json' \
  -H 'User-Agent: Hermes/1.0'

# Russia areas tree
curl -s 'https://api.hh.ru/areas/113' \
  -H 'Accept: application/json' \
  -H 'User-Agent: Hermes/1.0'

# Dictionaries
curl -s 'https://api.hh.ru/dictionaries' \
  -H 'Accept: application/json' \
  -H 'User-Agent: Hermes/1.0'
```

## Prefer the local CLI when available

```bash
hh-ru --json roles
hh-ru --json areas --query Екатеринбург
hh-ru --json vacancies --text Python --area 1 --per-page 10
```

Do not relay raw response headers to the user; redact `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, and API-key-like headers.
