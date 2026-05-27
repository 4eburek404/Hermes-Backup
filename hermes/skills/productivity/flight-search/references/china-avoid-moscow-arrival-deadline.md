# RU→China with “avoid Moscow” and arrival-deadline constraints

Use this reference when the user asks for Екатеринбург/Russia-origin flights to China airports and says arrival must be by a certain morning/date, with a preference like “желательно без пересадки в Москве”.

## Learned pattern

The compact `route live-assemble --agent-brief` can correctly rank operational one-stop options through Moscow, but may clip non-Moscow options or omit enough details to compare them. Do not conclude “only Moscow is viable” from the compact report alone when the user explicitly prefers non-Moscow.

## Probe sequence

1. Normalize destination airports separately, not just the city/country:
   - Guangzhou: `CAN`.
   - Shenzhen: `SZX`.
2. If the user gives only an arrival deadline (e.g. “прилёт не позже утра 15 июля”), pick a working assumption and state it in the final answer:
   - default morning cutoff: local arrival before 12:00;
   - search the latest plausible departure date first (e.g. 14 July), then the previous date (e.g. 13 July) if needed.
3. Run the Golden Path compact report for each serious airport/date pair:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json route live-assemble SVX CAN \
  --depart-date YYYY-MM-DD --return-date YYYY-MM-DD --profile business --agent-brief
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json route live-assemble SVX SZX \
  --depart-date YYYY-MM-DD --return-date YYYY-MM-DD --profile business --agent-brief
```

4. Escalate to narrow provider probes when non-Moscow is decision-critical:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json kb-search SVX CAN --depart-date YYYY-MM-DD --limit 100
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json kb-search CAN SVX --depart-date RETURN_DATE --limit 100
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json kb-search SVX SZX --depart-date YYYY-MM-DD --limit 100
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json kb-search SZX SVX --depart-date RETURN_DATE --limit 100
```

5. Post-filter normalized `offers[].flights`:
   - reject Moscow airports in any segment when comparing non-Moscow options: `SVO`, `DME`, `VKO`, `ZIA`, and city code `MOW` if present;
   - outbound must arrive before the stated deadline/cutoff in destination local time;
   - separate one-stop from two-stop options; for business travel, a two-stop return is a fallback unless no one-stop non-Moscow option exists;
   - compute elapsed time from first departure to final arrival using the ISO timestamps already in the normalized offer.

## Wording rules

- “Желательно без Москвы” is a preference, not an absolute hard filter. Present the best non-Moscow option first if viable, then show a Moscow backup if it is materially cleaner.
- Do not call separate outbound/return provider offers a protected round trip. Say “ориентир за пару one-way предложений” or similar unless a booking screen/GDS/airline fare proves a single protected round-trip order.
- If using “morning” as before noon, state that assumption.
- For China airport alternatives, compare airport practicality, stops, elapsed time, and arrival deadline before price.

## Example outcome shape

- Recommendation: `CAN` if it has a workable non-Moscow outbound by the deadline and a tolerable return.
- Alternatives: `SZX` if it satisfies the deadline but requires two stops or costs materially more.
- Backup: Moscow one-stop when it is operationally much cleaner, but keep it clearly labeled as violating the preference.
