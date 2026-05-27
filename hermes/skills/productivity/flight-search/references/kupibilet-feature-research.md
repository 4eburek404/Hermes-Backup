# KupiBilet feature research notes

Use when the user asks about KupiBilet capabilities, "фишки", checkout semantics, add-ons, or how to interpret KupiBilet search results operationally.

Session researched live on 2026-05-25 from KupiBilet public site/help pages and the runtime flight-search CLI.

## Source URLs consulted

- Main site / positioning: `https://www.kupibilet.ru`
- About: `https://www.kupibilet.ru/about`
- Help center: `https://www.kupibilet.ru/help`
- App page: `https://www.kupibilet.ru/app`
- Sales / "лазейки": `https://www.kupibilet.ru/sales`
- Price map: `https://www.kupibilet.ru/price-map`
- Smart route help: `https://www.kupibilet.ru/help/oformlenie-i-pokupka-aviabiletov/sub/obshchaya-informaciya/art/chto-takoe-smart-marshrut`
- Smart route blog: `https://www.kupibilet.ru/blog/chto-takoe-smart-marshruty-i-pochemu-tak-deshevle-letat`
- Extra services overview: `https://www.kupibilet.ru/blog/dopolnitelnye-uslugi-kupibileta`
- Online check-in: `https://www.kupibilet.ru/help/uslugi-i-akcii/sub/dopolnitelnye-uslugi/art/onlayn-registraciya`
- Important flight notifications: `https://www.kupibilet.ru/help/uslugi-i-akcii/sub/dopolnitelnye-uslugi/art/vazhnye-uvedomleniya-o-reyse`
- Priority support: `https://www.kupibilet.ru/help/uslugi-i-akcii/sub/dopolnitelnye-uslugi/art/prioritetnaya-podderzhka`
- Trip guarantee: `https://www.kupibilet.ru/help/uslugi-i-akcii/sub/dopolnitelnye-uslugi/art/garantiya-poezdki`
- KupiBilet refund add-on: `https://www.kupibilet.ru/help/uslugi-i-akcii/sub/dopolnitelnye-uslugi/art/vozvrat-ot-kupibilet`
- Legacy/non-refundable refund article: `https://www.kupibilet.ru/help/uslugi-i-akcii/sub/dopolnitelnye-uslugi/art/vozvrat-dazhe-nevozvratnogo-bileta`
- Add baggage after purchase: `https://www.kupibilet.ru/help/oformlenie-i-pokupka-aviabiletov/sub/dopolnitelnyy-bagazh/art/kak-dobavit-bagazh-posle-pokupki-bileta`
- Meal selection: `https://www.kupibilet.ru/help/uslugi-i-akcii/sub/dopolnitelnye-uslugi/art/pitanie-na-bortu`
- Bonus accrual/use: `https://www.kupibilet.ru/help/lichnyy-kabinet/sub/bonusnaya-programma/art/kak-nachislyayutsya-bonusnye-bally`, `.../art/kak-ispolzovat-bonusnye-bally`, `.../art/bally-za-vozvrat`
- Payment methods / currency: `https://www.kupibilet.ru/help/oformlenie-i-pokupka-aviabiletov/sub/oplata/art/chem-otlichayutsya-tri-sposoba-oplaty`, `.../art/mozhno-li-oplatit-bilety-na-sayte-esli-valyuta-moey-karty-otlichna-ot-rubley`
- Refund/exchange: `https://www.kupibilet.ru/help/vozvrat-ili-obmen-aviabiletov/sub/vozvrat/art/kak-vernut-bilet`, `.../art/skolko-kupibilet-beret-za-vozvrat-bileta`, `.../art/chto-takoe-vynuzhdennyy-vozvrat`, `.../art/chto-takoe-vozvrat-bileta-v-den-pokupki`, `.../sub/obmen/art/kak-pomenyat-datu-pereleta-i-skolko-eto-stoit`

## Operational interpretation

- KupiBilet is useful as OTA discovery and checkout evidence, not final airline/GDS proof.
- Distinguish `one KupiBilet order/checkout` from airline-responsible `single PNR / through-fare / baggage-through / missed-connection protection`.
- Smart routes are often separate tickets in one order. They may be cheaper but can require baggage reclaim/recheck, new check-in, passport/visa formalities, and independent refund/exchange rules per ticket.
- For business travel, use KupiBilet to discover candidates and price signals, then verify booking-screen/GDS/airline evidence for PNR, baggage, protection, terminals, and fare rules.

## Public feature summary

### Search and planning

- Flight and rail tickets; site says rail tickets are provided by partners and KupiBilet is not an official RZD resource.
- Price map and calendar-style date shopping.
- Sales / "лазейки" page: hot tickets, non-obvious routes, rail+air combinations, hidden-city, mirror ticket, smart routes, visa info, stopovers.
- Travel encyclopedia / guide pages for destination planning.
- Mobile app: offline ticket/receipt access, notebook/passenger autofill, push notifications, support, quick login, filters, online check-in, bonus points.

### Smart routes

- KupiBilet defines smart route as a rare/complex route composed from separate tickets.
- Advantages: can be materially cheaper and can include useful stopover time.
- Risks: passenger may need to register again, reclaim/recheck baggage, pass passport/visa control, and handle separate fare rules for each ticket.
- Do not present smart routes as protected connections unless KupiBilet Trip Guarantee or purchase-screen terms prove relevant protection.

### Add-ons and support

- Online check-in: KupiBilet registers within 24h before departure; user may indicate seat preferences but exact seat is not guaranteed. Some airlines charge per flight segment; if airline denies online check-in, KupiBilet says it refunds the service and passenger must check in at airport.
- Important flight notifications: SMS/push for schedule, gate, check-in/boarding times, check-in desks, baggage belt, aircraft model. Push requires the app.
- Priority support has three levels (minimum/standard/maximum); affects queue priority, SMS availability, and whether service fees apply for exchange/refund in eligible cases. It is per order.
- Trip Guarantee: covers cancellation, 5h+ delay for a ticket with one booking reference, and broken smart-route connection due to delay. User must contact KupiBilet as soon as possible and strictly no later than 2h after original departure time of the changed/cancelled flight. Does not cover passenger-caused problems such as no-show, self-changes, visa issues.
- KupiBilet refund add-on / `Возврат от Купибилет`: can return 90% of ticket cost if cancelled at least 48h before departure. Return may be via points immediately or money after airline approval. Does not cover partial use, add-ons, exchange, no-show, forced-return airline cases, or mass disruptions; service cost is usually non-refundable except same-day mistaken add-on cancellation.
- Baggage after purchase: via chat/order support; researched article states service fee 600 RUB. Airline deadlines differ (e.g. Aeroflot 24h; Pobeda 4h and after online check-in only airport purchase).
- Meals: available on supported airlines; availability and refundability depend on airline/time before departure.

### Payments, refunds, exchanges

- Payment methods: card or SBP. Card is broader but has transfer fee; SBP has no transfer fee per help page.
- Foreign-currency card: change site/app currency before checkout; conversion may occur and final capture can be days later.
- No deferred booking/payment hold: payment must start immediately after order creation.
- Refund service fee: direct KupiBilet site voluntary refund 10%; via third-party referral channel 16.9%; forced refund 0%.
- Card refund timing: via KupiBilet up to 30 days (often 1-7 business days); via airline up to 60 days.
- Same-day refund: request by 22:00 Moscow time; some airlines may allow only shorter windows such as 30 minutes, or block when checked in / under 48h / after check-in closed.
- Exchange cost: airline penalty + fare difference + KupiBilet service fee. Researched article states 1,700 RUB per ticket for KupiBilet purchase, 2,500 RUB per ticket via third-party purchase. Cannot exchange to another airline.

### Bonuses

- Help page: points accrue 1%-1.5% for tickets in the app depending on status and 3%-4.5% for additional services; site purchases accrue mainly for extra services. Points accrue next day after departure and expire after 1 year from accrual/spend event.
- Regular points: 1 point = 1 RUB; spend 500-2,000 per order with order-value constraints; may be unavailable for some airlines/payment methods (e.g. Nordwind or `pay through airline`).
- Points from `Возврат от Купибилет`: separate bucket, not combined with regular points; can pay nearly the whole new ticket with only 100 RUB paid by card/other method, subject to exclusions.
- Note discrepancy: app page showed `Гуру` ticket cashback as 1.45%, help page showed 1.5%; verify current account/checkout before quoting exact status percent as firm.

## Runtime CLI evidence checked

Live KupiBilet endpoint worked on 2026-05-25:

```bash
cd ~/.hermes/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json kb-search SVX MOW \
  --depart-date 2026-06-08 --limit 2 --cache-ttl-seconds 0
```

Returned HTTP 200, `source_url=https://api-rs-lb.kupibilet.ru/frontend_search`, request body with one `trips` entry, raw variants/offers and direct SVX-SVO flights.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json kb-roundtrip SVX MOW \
  --depart-date 2026-06-08 --return-date 2026-06-10 --limit 1 --cache-ttl-seconds 0
```

Returned HTTP 200, request body with two `trips` entries, round-trip fare package, baggage/hand-luggage fields, seats_left, and journeys split outbound/return.

## Answering pattern

For future user-facing KupiBilet feature answers:

1. Start with the practical operational conclusion: good for discovery/price/smart routes; verify protected-ticket details before business travel purchase.
2. Group features by use case: search/lazeyki, smart routes, add-ons, app/account, payments/refunds/exchange, bonuses.
3. Mark high-risk tricks (hidden city, mirror ticket, smart route separate tickets) as risk-bearing rather than recommendations.
4. When citing add-ons, include decision-critical deadlines/limits: Trip Guarantee 2h claim window, KupiBilet Refund 48h before departure, same-day refund by 22:00 Moscow, baggage deadlines by airline.
5. Mention evidence date and that public help pages/checkout terms can change; ask to re-check current checkout for exact price/coverage before purchase.
