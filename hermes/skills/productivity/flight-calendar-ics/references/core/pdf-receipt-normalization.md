# PDF receipt normalization feature

Use this when a local airline receipt PDF is the source evidence, or when a carrier receipt PDF contains enough itinerary data but no supported carrier lookup URL is available.

This is a normalization feature: private PDF evidence → calendar-safe canonical itinerary JSON → CLI-owned `build make` bundle. Do not treat it as permission to dump full PDF text into chat or to bypass the normal envelope verification.

## Pattern

1. Keep the original PDF private. Do not dump full text or passenger/payment fields into chat.
2. Extract text locally with PyMuPDF, or OCR only if the PDF has no embedded text.
3. Build a canonical itinerary JSON that contains only calendar-safe operational fields:
   - `flight_number`, `carrier`, `carrier_code`
   - departure/arrival airport IATA codes, city names, local datetimes, and IANA timezones
   - optional non-sensitive baggage/cabin notes
4. Omit passenger names, PNR/booking refs, ticket/document numbers, payment data, contacts, birth dates, and booking deep links unless the user explicitly wants those embedded in the local `.ics` file.
5. Verify ambiguous airport names with public schedule/airport evidence when the PDF gives only city names. Example: Beijing for Ural Airlines SVX route maps to PKX/Daxing, not a generic `BJS` city code.
6. Run the CLI-owned bundle path with canonical JSON:

```bash
python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json build make --input /private/itinerary.json
```

7. Require the same envelope checks as the happy path before sending: schema version, `ok=true`, `command=build`, segment count, `verification.ok=true`, and existing `data.ics_path`.

## Minimal canonical JSON shape

```json
{
  "schema_version": "flight-calendar-ics-itinerary.v1",
  "calendar_name": "Carrier route",
  "source": {"kind": "pdf", "description": "Airline itinerary receipt PDF"},
  "flights": [
    {
      "flight_number": "U6 775",
      "carrier": "Ural Airlines",
      "carrier_code": "U6",
      "departure": {
        "airport": "SVX",
        "city": "Yekaterinburg",
        "local": "2026-06-22T00:40",
        "tz": "Asia/Yekaterinburg"
      },
      "arrival": {
        "airport": "PKX",
        "city": "Beijing",
        "local": "2026-06-22T09:55",
        "tz": "Asia/Shanghai"
      }
    }
  ]
}
```

Treat dates without years carefully: infer the year only from reliable receipt metadata such as ticket sale date or explicit context, and label the inference if reporting it in chat.
