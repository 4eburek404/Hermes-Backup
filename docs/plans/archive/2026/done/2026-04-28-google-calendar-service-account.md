# Plan: Google Calendar через сервисный аккаунт (без OAuth пользователя)

**Date:** 2026-04-28
**Status:** done ✓
**Goal:** Подключить Google Calendar через сервисный аккаунт Google Cloud для чтения и потенциальной записи событий без пользовательского OAuth.

## Context

- Пользователь: ks.orlov@gmail.com, не хочет пользовательский OAuth
- Почта уже работает через Himalaya + App Password
- CalDAV через App Password не сработал (loginRequired)
- Сервисный аккаунт — альтернатива: JSON-ключ вместо OAuth
- Требуется расшарить календарь на email сервисного аккаунта вручную (1 раз)

## Steps

### 1. Установить pipx и gcalcli

```bash
apt install pipx  # или pip install --user pipx
pipx ensurepath
pipx install gcalcli
```

### 2. Создать сервисный аккаунт (со стороны пользователя)

Инструкция пользователю:
1. https://console.cloud.google.com — создать/выбрать проект
2. APIs & Services → Library → включить **Google Calendar API**
3. APIs & Services → Credentials → Create Credentials → **Service Account**
4. Название любое (например `hermes-calendar`), роль: Basic → Viewer (или Editor для записи)
5. После создания → Keys → Add Key → JSON → скачается файл
6. Прислать JSON-файл (путь или содержимое)

### 3. Расшарить календарь на сервисный аккаунт

После получения JSON:
1. Из JSON извлечь `client_email` (вида `...@...iam.gserviceaccount.com`)
2. Пользователь в настройках Google Календаря: шестерёнка → Настройки → выбрать календарь → «Доступ» → Добавить пользователя → вставить `client_email` → права: «Просмотр» или «Изменение»

### 4. Сохранить ключ и проверить доступ

Итоговая реализация: ключ хранится в защищённой конфигурации; точный путь к key file не документировать. `gcalcli 4.5.1` больше не поддерживает ожидаемый флаг `--sa`, поэтому доступ проверяется через Python `google-api-python-client` + `google.oauth2.service_account.Credentials`.

### 5. Тестовые операции

- Чтение проверено через Python Google Calendar API.
- ACL-проверка показывает, что сервисный аккаунт имеет `writer` доступ. Дайджесты календаря могут использовать `calendar.readonly` scope намеренно для безопасного чтения, но сам календарь не расшарен как read-only.

## Verification

- [x] pipx + gcalcli установлены, но `gcalcli --sa` оказался непригоден в v4.5.1
- [x] JSON-ключ получен и сохранён с chmod 600 (точный путь не документировать)
- [x] Calendar API включён в Google Cloud проекте
- [x] Календарь расшарен на `client_email`
- [x] Python `google-api-python-client` показывает события
- [x] Права на запись по ACL проверены: service account имеет роль `writer`; отдельные write-операции выполнять только после явного подтверждения пользователя.

## Risks

- Сервисный аккаунт требует Google Cloud проект (один раз)
- Календарь нужно расшарить вручную — без этого API вернёт пустой список
- JSON-ключ даёт доступ только к тем календарям, которые явно расшарены
- Если аккаунт корпоративный (Google Workspace) — админ может блокировать расшаривание внешним сервисным аккаунтам

## Notes

- Сервисный аккаунт НЕ считается пользовательским OAuth — нет браузера, редиректов, consent screen
- Тот же ключ можно использовать для Gmail API, Drive API и т.д. в будущем
- `gcalcli 4.5.1` не использовать как основной путь для service account; рабочий путь — Python Google API client.
