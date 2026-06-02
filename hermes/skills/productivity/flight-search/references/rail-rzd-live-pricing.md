# Rail/RZD Live Pricing Cross-Check

Use this only as a bounded adjacent comparison after a flight search, when the user asks whether train tickets are cheaper or asks for rail prices on the same route/date. It is not a full rail-booking or purchase skill.

## Source policy

For Russian rail availability and prices, use official RZD/pass.rzd data as the source of truth:

- Human/source layer: official RZD (`rzd.ru` / `ticket.rzd.ru`).
- Agent read-only layer: `https://pass.rzd.ru/timetable/public/ru`.

Do not use Яндекс/Туту/UFS/Ozon/OneTwoTrip or other aggregators as a default fallback for seats or prices. If `rzd.ru` / `pass.rzd.ru` is unavailable, say plainly: «официальная выдача РЖД сейчас недоступна, наличие мест и цены проверить не могу». Do not replace official-source failure with aggregator estimates unless the user explicitly asks for non-official advisory context.

Do not infer “no trains” or “no seats” from one failed request. Treat request/network/parser failures as source/runtime failure unless the official response itself says there are no trains or seats.

## What the read-only endpoint can support

Use the endpoint for:

- train schedule by route and date;
- seat availability by car type;
- current tariff buckets by car/service class;
- train numbers, stations, local departure/arrival, and time in way;
- electronic-registration and carrier fields when present.

It is not booking or purchase evidence. Final fare, exact seat/car, fees, refund rules, meals/service details, and purchase eligibility must be checked on the official RZD booking screen.

## Station codes

Resolve station codes through the official suggester:

```text
GET https://pass.rzd.ru/suggester?lang=ru&compactMode=y&stationNamePart=<UPPERCASE_QUERY>
```

Practical rules:

- Use uppercase query text, for example `ЕКАТЕРИНБУРГ`, `ТОМСК`.
- Select the exact station when route scope depends on it; do not silently collapse station and city scope.
- Example codes from the checked SVX/Екатеринбург ↔ Томск case:
  - Екатеринбург-Пассажирс: `2030000`
  - Томск city/all-stations: `2028156`
  - Томск-2: `2028170`

Treat these as examples; for a new city/station, check the suggester first.

## Route/RID workflow

The route endpoint is a two-step RID workflow.

Initial request:

```text
POST https://pass.rzd.ru/timetable/public/ru
layer_id=5827
dir=0
tfl=3
checkSeats=1
code0=<origin_station_code>
code1=<destination_station_code>
dt0=<DD.MM.YYYY>
```

Fetch request after the initial response returns `RID` / `REQUEST_ID`:

```text
POST https://pass.rzd.ru/timetable/public/ru
layer_id=5827
rid=<RID_FROM_FIRST_RESPONSE>
```

Operational details:

- `dir=0` means one-way.
- `tfl=3` means trains.
- `checkSeats=1` requests availability/seat buckets.
- `dt0` format is `DD.MM.YYYY`.
- Use browser-like headers: `Accept: application/json`, `User-Agent`, `Referer: https://ticket.rzd.ru/`.
- Keep the same session/cookies between the initial request and RID fetch.
- Poll only a few times with a short sleep; avoid aggressive or infinite polling.
- For round trips, run two separate one-way queries with swapped `code0`/`code1` and the return date. Do not rely on an aggregator round-trip fallback.

## Response fields to read

Read `tp[0].list[]`; each train may include:

- `number` / `number2` — train number;
- `route0`, `route1`, `carrier` — route and carrier labels;
- `station0`, `station1`, `code0`, `code1` — stations;
- `localDate0`, `localTime0`, `localDate1`, `localTime1` — local dates/times;
- `timeInWay` — travel time;
- `elReg` — electronic registration flag;
- `cars[]` — car types, seats, and tariffs.

In `cars[]`, read:

- `typeLoc` / `type` — car type (`Плацкартный`, `Купе`, `СВ`, etc.);
- `freeSeats` — free seats;
- `tariff` — current tariff;
- `servCls` — service class;
- `disabledPerson` when accessibility context matters.

## Output rules

For Russian rail comparison answers:

- Start with the evidence status: «проверил официальную выдачу РЖД» or «официальная выдача РЖД недоступна».
- Show one-way options by train/date, then round-trip minimums by class when comparing with flights.
- Show at least the practical car classes when present: плацкарт/купе/СВ, free seats, and “price from”.
- Include travel-time cost: trains may be cheaper but can consume roughly 26–30h each way on long domestic routes.
- Compare with the flight option only after calculating totals, not by intuition.
- State that the price is read-only/dynamic and final purchase conditions must be confirmed on the official RZD booking screen.
- Do not mix official RZD tariffs with aggregator prices.
- Do not claim ticket purchase, exact seat choice, refund terms, meals/service details, or accessibility eligibility unless verified on the booking screen.

## Python probe skeleton

```python
import requests, time, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def rzd_routes(code0, code1, dt0):
    session = requests.Session()
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://ticket.rzd.ru/',
    }
    url = 'https://pass.rzd.ru/timetable/public/ru'
    params = {
        'layer_id': 5827,
        'dir': 0,
        'tfl': 3,
        'checkSeats': 1,
        'code0': code0,
        'code1': code1,
        'dt0': dt0,
    }
    for _ in range(8):
        data = session.post(url, data=params, headers=headers, timeout=30, verify=False).json()
        if data.get('result') in ('RID', 'REQUEST_ID'):
            params = {'layer_id': 5827, 'rid': data.get('RID') or data.get('rid')}
            time.sleep(2)
            continue
        return data
    return data
```
