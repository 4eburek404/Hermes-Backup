# News/RSS follow-up extraction notes

Use when a user asks for more detail on a news item found via search/RSS, especially Russian travel/business-travel sources.

## What worked in this session

- Google News RSS links can resolve to large Google wrapper pages that do not expose the publisher article text to simple extraction. Do not treat a successful HTTP 200 from Google News as article content.
- Search the suspected publisher site directly using the exact headline or distinctive phrase.
  - Example: Rata-news search exposed direct URLs for `«Мой Агент» соединит Россию и Азию...` when Google wrapper extraction was not useful.
  - Command pattern:
    ```bash
    curl -sL 'https://www.ratanews.ru/search/?q=<urlencoded headline>' | grep -i -A3 -B3 '<distinctive phrase>'
    ```
- Once the direct publisher URL is found, run:
  ```bash
  ~/.local/bin/article --json read '<publisher-url>'
  ```
- For RST / Russian Union of Travel Industry pages, the listing `/novosti.html` contains direct article links in static HTML and can be grepped for headline fragments.
  - Example direct URL shape:
    `https://rst.ru/novosti/novosti-kompanii/<slug>.html`
- Official event landing pages may be Tilda/JS-heavy and noisy, but `article --json read` can still extract useful body text. Summarize only verified event details and label marketing claims as such.

## Evidence pattern to preserve in answers

When summarizing a news item, distinguish:

- checked source article facts: title, publication, date, direct URL, extracted text;
- official landing-page facts: date, venue, program, speakers;
- interpretation: market implications, operational risks, and relevance to the user.

## Pitfalls

- Do not answer from a previous RSS headline alone when the user asks for details. Follow through to the direct publisher article or official page.
- Do not assume Google News wrapper text is the publisher article. Verify direct URL content.
- If extraction output is huge/noisy, use title/date/speaker/program fragments found in the body and avoid overclaiming details not explicitly present.