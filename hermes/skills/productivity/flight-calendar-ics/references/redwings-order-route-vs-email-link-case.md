# Red Wings: order route is not the same as the email manage-booking link

## Durable lesson

For Red Wings/Websky calendar generation, distinguish these two URL classes:

- `https://flyredwings.com/booking/#/find/<PNR>/<SECRET>/Submit` — email/manage-booking access route. This is the preferred one-click booking URL for a calendar event when the user can provide it.
- `https://flyredwings.com/booking/#/booking/<ORDER_ID>/order` — already-opened order route. Treat as private evidence that a booking exists, but do not assume it is a portable reopen link or that it contains/derives the `<SECRET>` needed for `#/find/.../Submit`.

## Operational pattern

1. Use the PDF/ticket as the primary source for flight facts: carrier, route, dates/times, airports, flight number, duration, baggage/seat/ticket details when present.
2. If the user wants the calendar event to reopen the Red Wings booking and only provides a PDF/screenshot/order page, ask for the original email/manage-booking link shaped `#/find/<PNR>/<SECRET>/Submit`.
3. Do not guess `<SECRET>` from passenger surname, PNR, order id, or ticket data.
4. If no email link is available, generate the `.ics` with flight facts and either omit the direct booking URL or use only a non-credentialed general manage-booking page, clearly stating the limitation.
5. Keep all raw PNRs, secrets, order ids, passenger data, contacts, documents, and full manage-booking URLs out of chat/logs; include a working private URL only inside the owner-only `.ics` when intentionally requested.

## Verification points

- The `.ics` has one `VEVENT` per segment, UTC `DTSTART`/`DTEND`, local times preserved in `DESCRIPTION`, and requested reminders.
- Chat summary redacts booking credentials and personal data.
- If documenting the workflow in the repo/skill, replace concrete route examples with placeholders and run a secret scan over staged additions before committing.
