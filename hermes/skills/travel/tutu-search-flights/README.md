# tutu-search-flights

Skill содержит CLI для поиска авиабилетов через Tutu, записанные MCP fixtures, детерминированные тесты и исполняемые спецификации.

## Локальная установка

Запускайте команды из этой директории. Укажите `PYTHON` — интерпретатор, в который нужно установить зависимости. На Mac для разработки Hermes-Backup:

```sh
export PYTHON=/Users/home/.venvs/hermes-backup/bin/python
uv pip install --python "$PYTHON" --require-hashes -r requirements-dev.txt
make check
```

Зависимости из lock-файла устанавливаются в выбранный интерпретатор. Команды не создают виртуальное окружение и не запускают `uv sync` для общего окружения.

## Файл блокировки

`requirements-dev.txt` — универсальный lock с хэшами, собранный из `pyproject.toml`. Чтобы обновить его, запустите из этой директории:

```sh
uv pip compile pyproject.toml --extra dev --universal --generate-hashes --no-annotate -o requirements-dev.txt
```

Проверьте сгенерированный файл перед установкой или коммитом.

## Проверки и CI

- `make check` запускает все тесты без live-маркера, Ruff lint и проверку форматирования, а также проверку команд в документации.
- `make spec` запускает детерминированные исполняемые спецификации продукта.
- `make live` явно включает smoke test реального Tutu MCP. Команда отправляет сетевой запрос и не входит в `make check`.
- `make discover` обновляет исследовательские данные через реальный Tutu MCP.
- `make clean` удаляет локальные кэши Python-инструментов.

GitHub Actions запускает workflow для pull request и push с изменениями в этом skill или в его workflow; его также можно запустить вручную. Workflow устанавливает зависимости с проверкой хэшей на Ubuntu с Python 3.13 и выполняет `make check`. CI не запускает `make live` и `make discover`, секреты Tutu не используются.

Workflow подготовлен локально. Эта проверка не подтверждает успешный запуск GitHub Actions или обязательность workflow в branch protection.
