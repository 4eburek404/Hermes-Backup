"""Тестовая привязка к продукту; не часть публичного API или его архитектуры.

При первой реализации здесь подключается её реальная точка входа и, если нужно,
проецируется её результат в наблюдения из test_successful_search.py. Нельзя
строить наблюдения из fixture: их единственный источник — результат продукта.
"""


def search(arguments, call_tool):
    # Импорт внутри вызова: сценарий собирается и доходит до действия (RED),
    # а не ломает сборку остальных тестов. Реализации в baseline ещё нет.
    from tutu_search_flights import search as product_search

    return product_search(arguments, call_tool=call_tool)
