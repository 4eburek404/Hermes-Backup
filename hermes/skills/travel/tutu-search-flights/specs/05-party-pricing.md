# S4 — цена сохраняет связь с составом пассажиров

## Дано

Используется записанный запрос `fixtures/avia/party-2a-1c.json` для двух взрослых
и одного ребёнка вместе с raw ответом Tutu.

## Когда

Продукт обрабатывает этот ответ.

## Тогда

- сохраняется фактический состав пассажиров из `meta.pricing.passengers`;
- значение `party_total` трактуется как цена всей группы;
- цена каждого тарифа остаётся равной цене этого тарифа в источнике и не умножается
  повторно на число пассажиров;
- условия тарифа остаются привязаны к той же цене;
- для каждого варианта сохраняются `currency` и исходные значения условий
  `baggage`, `cabin_baggage`, `refundable`, `changeable` и `exchange`.

## Исполнение

Проверка выполняется на записанном raw MCP response без сети:
[tests/test_party_pricing.py](../tests/test_party_pricing.py) — node ID:
`tests/test_party_pricing.py::test_party_total_price_is_not_multiplied_again`.
