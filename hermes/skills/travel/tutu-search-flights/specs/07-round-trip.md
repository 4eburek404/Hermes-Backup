# S6 — round-trip сохраняет оба плеча

## Дано

Используется записанный ответ `fixtures/avia/round-trip.json` с перелётом туда-обратно.

## Когда

Продукт обрабатывает предложение.

## Тогда

- сохраняется признак round-trip;
- outbound и return остаются отдельными legs в исходном порядке;
- для каждого плеча сохраняются длительность, сегменты, номера рейсов, перевозчики,
  аэропорты и локальные времена;
- основной origin/destination описывает outbound, а не склеивает начало outbound
  с концом return;
- времена обратного вылета и прилёта сохраняются, когда источник их сообщает.

## Исполнение

Проверка выполняется на записанном raw MCP response без сети:
[tests/test_round_trip.py](../tests/test_round_trip.py) — node ID:
`tests/test_round_trip.py::test_round_trip_preserves_both_legs_and_outbound_route`.
