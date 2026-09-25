"""Тестовая привязка к реальной точке входа продукта.

Это test-only adapter, не публичный API и не часть архитектуры. Наблюдения берутся
из результата продукта, а не строятся из fixture. Функция поиска импортирует
production entry point лениво, чтобы ошибка импорта проявлялась при выполнении
сценария, а не при сборке остальных тестов.
"""


def search(arguments, call_tool):
    # Изначально lazy import позволил дойти до действия в начальном RED цикле,
    # пока production package ещё не был создан. Сохраняем его ради локализации
    # загрузки точки входа на момент вызова тестового сценария.
    from tutu_search_flights import search as product_search

    return product_search(arguments, call_tool=call_tool)
