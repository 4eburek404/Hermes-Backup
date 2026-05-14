# hh.ru API/Auth Reference

Detailed API/auth/reference material extracted from `SKILL.md` so the skill core stays focused on workflow, pitfalls, and verification.

## Authentication

### Without Token (Public API)
Most read endpoints work without auth but with **severe rate limits**:
- `/vacancies` (search) — **quickly banned after ~10-15 requests, ban lasts 3+ minutes**
- `/vacancies/{id}` — works, but `contacts` field hidden
- `/employers/{id}` — works
- `/areas`, `/dictionaries`, `/industries`, `/professional_roles` — more stable
- `/suggests/*` — works
- `/salary_statistics/dictionaries/*` — works

**Rate limit reality (tested):** After ~10-15 requests to `/vacancies` from one IP, API returns 403 for **3+ minutes**. No `X-RateLimit` headers in responses. Dict/reference endpoints are more tolerant but can also be blocked.

### Plan A: App Token (Client Credentials) — recommended starting point
Simplest, no user login needed. One-time generation. Sufficient for vacancy search, employers, reference data.

```
POST https://api.hh.ru/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET
```

- Token visible at https://dev.hh.ru/admin after generation
- Generates **1 time**; on regeneration the old token is revoked
- **Limit:** app token refresh max 1 time per 5 minutes (403 `app token refresh too early`)
- **No access to:** contacts, resumes, chats, webhooks, applicant-side operations

### Plan B: User Token (Authorization Code) — full access
Requires one-time browser login, then automated refresh.

**Step 1 — Authorize (user opens in browser):**
```
https://hh.ru/oauth/authorize?response_type=code&client_id=YOUR_CLIENT_ID
```
Optional params: `state`, `redirect_uri`, `code_challenge` + `code_challenge_method=S256` (PKCE).

**Step 2 — User grants access → redirected to `redirect_uri?code=XXX`:**
User copies `code` from URL bar.

**Step 3 — Exchange code for tokens:**
```
POST https://api.hh.ru/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&client_id=YOUR_CLIENT_ID&
client_secret=YOUR_CLIENT_SECRET&code=AUTH_CODE&redirect_uri=YOUR_REDIRECT_URI
```

**Step 4 — Refresh tokens (before access_token expires):**
```
POST https://api.hh.ru/token
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=YOUR_REFRESH_TOKEN
```

**Token lifecycle critical details:**
- `access_token` expires after `expires_in` seconds (typically ~7 days)
- `refresh_token` is **single-use** — using it twice → error `token has already been refreshed`
- Cannot refresh before `access_token` expires → error `token not expired`
- User password change → token deactivated (`token deactivated` error)
- Response: `access_token`, `refresh_token`, `token_type`, `expires_in`, `created_at`

**Invalidate token:** `DELETE /token` with `Authorization: Bearer <token>`

**redirect_uri rules (strict!):**
If app redirect_uri = `https://hh.ru`, then **only allowed:**
- `https://www.hh.ru` — subdomain
- `https://hh.ru/sub/path` — path extension
- `https://hh.ru?lang=RU` — query params

**Forbidden:**
- Different scheme (`http://hh.ru`)
- Different domain entirely
- Additional subdomain levels (`test.hh.ru`)
- Different path (`/oauths`)
- Different port (`:443`)

**Register app:** https://dev.hh.ru/admin — approval takes **up to 15 business days**.

**Auth error codes (403):**
| type | value | meaning |
|------|-------|---------|
| oauth | bad_authorization | token invalid or doesn't exist |
| oauth | token_expired | access_token expired, refresh it |
| oauth | token_revoked | token revoked by user |
| oauth | application_not_found | app deleted |
| oauth | user_auth_expected | app token used where user token required |

## Key Endpoints

### Vacancies Search
```
GET /vacancies?{params}
```

**Query params:**
| Param | Description | Example |
|-------|-------------|---------|
| `text` | Full-text search query | `text=Python+developer` |
| `area` | Region ID (from /areas) | `area=1` (Москва) |
| `industry` | Industry ID (from /industries) | `industry=7` (IT) |
| `specialization` | Professional field ID | `specialization=1.221` |
| `salary_from` | Min salary (RUB default) | `salary_from=100000` |
| `salary_to` | Max salary | `salary_to=200000` |
| `currency` | Currency code | `currency=RUR` |
| `experience` | Experience filter | `experience=noExperience` |
| `employment_type` | Employment type | `employment_type=full` |
| `schedule` | Work schedule | `schedule=remote` |
| `order_by` | Sort order | `order_by=salary_desc` |
| `page` | Page number (0-based) | `page=0` |
| `per_page` | Results per page (max 100) | `per_page=20` |
| `search_field` | Where to search | `search_field=name` |

**Response structure:**
- `found` — total results count
- `pages` — total pages
- `per_page` — results per page
- `items[]` — vacancy array with: id, name, salary, area, employer, experience, schedule, employment, type, relations, address

### Vacancy Detail
```
GET /vacancies/{id}
```
Returns full vacancy: name, description (HTML), key_skills[], salary, area, employer, contacts (auth required), experience, schedule, employment, address, vacancy_type, branded_description.

### Professional Roles (замена specializations)
```
GET /professional_roles
```
27 категорий с ролями. Ключевые категории:

| ID | Категория | Примеры ролей |
|----|-----------|---------------|
| 11 | Информационные технологии | BI-аналитик, DevOps, Аналитик, Бизнес-аналитик (+20 roles) |
| 26 | Высший и средний менеджмент | CEO, CIO, CMO, HRD, CLO (+10 roles) |
| 5 | Административный персонал | Администратор, Делопроизводитель, Курьер (+8 roles) |
| 14 | Закупки | Менеджер по закупкам, Специалист по тендерам |
| 44 | Услуги для бизнеса | Кадровые агентства, Колл-центры, Консалтинг |

Используйте `professional_role` вместо `specialization` в поиске вакансий.

### Salary Statistics (Банк данных заработных плат)
```
GET /salary_statistics/dictionaries/salary_areas       — Регионы для зарплатных данных (10 macro-areas)
GET /salary_statistics/dictionaries/salary_industries  — Отрасли для зарплатных данных
GET /salary_statistics/dictionaries/professional_areas — Профобласти и специализации
GET /salary_statistics/dictionaries/employee_levels    — Уровни компетенций
GET /salary_statistics/paid/salary_evaluation/{area_id}?position_name=...&industry=...
```

**Employee levels:**
| ID | Уровень |
|----|---------|
| `top_manager` | Первое лицо, руководитель подразделений |
| `function_manager` | Руководитель подразделения |
| `expert` | Эксперт  (>5 лет опыта) |
| `manager` | Линейный руководитель (3-5 лет) |
| `senior_specialist` | Ведущий специалист (от 3 лет) |
| `specialist` | Специалист (1-2 года) |
| `junior` | Начальный уровень (<1 года) |

**Salary area IDs (macro-regions, NOT the same as /areas):**
| ID | Регион |
|----|--------|
| 10001 | Москва и Московская область |
| 10002 | Санкт-Петербург и Ленинградская область |
| 10004 | Приволжский федеральный округ |
| 10007 | Сибирский федеральный округ |
| 10009 | Центральный федеральный округ |

### Suggests (Autocomplete)
```
GET /suggests/areas                       — Регионы
GET /suggests/companies                   — Организации
GET /suggests/professional_roles           — Профессиональные роли
GET /suggests/skill_set                    — Ключевые навыки
GET /suggests/vacancy_search_keyword       — Ключевые слова для поиска вакансий
GET /suggests/vacancy_positions            — Должности вакансий
GET /suggests/resume_search_keyword        — Ключевые слова для поиска резюме
GET /suggests/positions                    — Должности резюме
GET /suggests/educational_institutions     — Учебные заведения
GET /suggests/fields_of_study              — Специализации
GET /suggests/area_leaves                  — Листовые регионы
```

### Vacancy Search (Enhanced)
```
GET /vacancies?text=...&area=...&professional_role=...&salary_from=...&order_by=...
```

**Additional params not in original skill:**
| Param | Description | Example |
|-------|-------------|---------|
| `professional_role` | Role ID from /professional_roles | `professional_role=156` (BI-аналитик) |
| `employer_id` | Filter by employer | `employer_id=12345` |
| `currency` | Currency code | `currency=RUR` |
| `only_with_salary` | Only vacancies with salary | `only_with_salary=true` |
| `premium` | Premium vacancies only | `premium=true` |
| `accept_incomplete_resumes` | Accept incomplete resumes | `accept_incomplete_resumes=true` |
| `search_field` | Where to search | `search_field=name`, `search_field=description` |
| `order_by` | Sort order | `publication_time`, `salary_desc`, `relevance` |
| `label` | Vacancy label filter | `label=with_salary`, `label=not_from_agency` (repeatable) |
| `work_format` | Work format | `work_format=REMOTE`, `HYBRID`, `ON_SITE`, `FIELD_WORK` |
| `employment_form` | Employment form | `employment_form=FULL`, `PART`, `PROJECT`, `FLY_IN_FLY_OUT`, `SIDE_JOB` |

**Vacancy labels (param `label`, repeatable):**
| ID | Description |
|----|-------------|
| `with_salary` | Указан доход |
| `not_from_agency` | Без вакансий агентств |
| `accept_handicapped` | Доступно для людей с инвалидностью |
| `accredited_it` | Аккредитованные ИТ-компании |
| `low_performance` | Меньше 10 откликов |
| `internship` | Стажировка |
| `accept_kids` | Доступно от 14 лет |
| `accept_teens` | Доступно от 16 лет |
| `night_shifts` | Вечерние/ночные смены |

**Work formats (param `work_format`):**
| ID | Name |
|----|------|
| `ON_SITE` | На месте работодателя |
| `REMOTE` | Удалённо |
| `HYBRID` | Гибрид |
| `FIELD_WORK` | Разъездной |

**Employment forms (param `employment_form`, differs from `employment_type`):**
| ID | Name | Duration |
|----|------|----------|
| `FULL` | Полная | permanent |
| `PART` | Частичная | permanent |
| `PROJECT` | Проект | temporary |
| `FLY_IN_FLY_OUT` | Вахта | permanent |
| `SIDE_JOB` | Подработка | temporary |

### Employer Vacancies
```
GET /employers/{id}/vacancies?per_page=10&page=0
```
Lists all open vacancies for a specific employer.

### Similar Vacancies (no auth)
```
GET /vacancies/{id}/similar_vacancies
```
Find vacancies similar to a given one.

### Related Vacancies (no auth)
```
GET /vacancies/{id}/related_vacancies
```

### Chats (AUTH REQUIRED)
```
GET  /common/chats                          — List chats
GET  /common/chats/{id}/messages            — Chat messages
POST /common/chats/{id}/messages            — Send message
GET  /common/chats/counters/unread          — Unread counters
```

### Webhooks (AUTH REQUIRED)
```
GET    /webhook/subscriptions               — List subscriptions
POST   /webhook/subscriptions               — Subscribe
PUT    /webhook/subscriptions/{id}           — Update subscription
DELETE /webhook/subscriptions/{id}           — Delete subscription
```

### Vacancy Stats (AUTH REQUIRED for employer's vacancies)
```
GET /vacancies/{id}/stats                   — Views, responses stats
GET /vacancies/{id}/visitors                — Who viewed the vacancy
```

### Reference Data (no auth required)

| Endpoint | Description |
|----------|-------------|
| `GET /areas` | Countries tree |
| `GET /areas/113` | Russia → regions → cities |
| `GET /dictionaries` | Employment types, schedules, experience levels, currencies, etc. |
| `GET /industries` | Industry tree |
| `GET /specializations` | Professional fields tree (auth required) |

### Key Area IDs (Russia = 113)

**⚠ IDs уникальны, но дерево трёхуровневое:** страна → регион → город. Запрашивай `GET /areas/113` и ищи по имени — не хардкодь.

| ID | Город/Регион |
|----|---------------|
| 1 | Москва |
| 2 | Санкт-Петербург |
| 45 | Екатеринбург (внутри Свердловская область) |
| 1291 | Нижний Тагил (внутри Свердловская область) |
| 4 | Новосибирск |
| 88 | Казань (внутри Татарстан) |
| 54 | Красноярск |
| 66 | Нижний Новгород |
| 76 | Ростов-на-Дону |

**Почему не хардкодить:** ID 14 — это Архангельск (внутри Архангельская область), а не Казань. ID 3 — Екатеринбург в одной версии дерева, но может отличаться. Всегда подтверждай через API по имени.

### Dictionary Values

**Experience (`experience`):**
- `noExperience` — Нет опыта
- `between1And3` — От 1 года до 3 лет
- `between3And6` — От 3 до 6 лет
- `moreThan6` — Более 6 лет

**Employment type (`employment_type`):**
- `full` — Полная занятость
- `part` — Частичная занятость
- `project` — Проектная работа
- `volunteer` — Волонтерство
- `probation` — Стажировка

**Schedule (`schedule`):**
- `fullDay` — Полный день
- `shift` — Сменный график
- `flexible` — Гибкий график
- `remote` — Удаленная работа
- `flyInFlyOut` — Вахтовый метод

**Business trip readiness (`business_trip_readiness`):**
- `ready` — Готов к командировкам
- `sometimes` — Готов к редким командировкам
- `never` — Не готов к командировкам

**Education level (`education_level`):**
- `secondary` — Среднее
- `special_secondary` — Среднее специальное
- `unfinished_higher` — Неоконченное высшее
- `higher` — Высшее
- `bachelor` — Бакалавр
- `master` — Магистр
- `candidate` — Кандидат наук
- `doctor` — Доктор наук

**Vacancy type (`vacancy_type`):**
- `open` — Открытая
- `anonymous` — Анонимная
- `closed` — Закрытая
- `direct` — Рекламная

**Vacancy billing type (`vacancy_billing_type`):**
- `free` — Бесплатная
- `standard` — Стандарт
- `standard_plus` — Стандарт плюс
- `premium` — Премиум

**Currency (`currency`, selected from /dictionaries):**
- `RUR` — Рубли ₽ (default, rate=1.0)
- `USD` — Доллары $ (rate from dict)
- `EUR` — Евро € (rate from dict)
- `BYR`, `KZT`, `UAH`, `AZN`, `GEL`, `KGS`, `UZS` — others

### Key Industry IDs

| ID | Industry |
|----|----------|
| 7 | IT, системная интеграция, интернет |
| 24 | Металлургия, металлообработка |
| 43 | Финансовый сектор |
| 44 | Услуги для бизнеса |
| 45 | Добывающая отрасль |
| 47 | Нефть и газ |
| 48 | Медицина, фармацевтика |
| 50 | Гостиницы, рестораны, общепит |
