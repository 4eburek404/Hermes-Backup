# Dashboard OpenAI Codex model list fix

## Цель
Dashboard должен показывать полный список OpenAI Codex моделей из актуального источника, а не обрезанные 7 моделей.

## Проверки
- Воспроизведено: запущенный Dashboard API на `127.0.0.1:9119/api/model/options` возвращал `openai-codex.total_models = 7`.
- Проверено в runtime-коде после патча: `provider_model_ids('openai-codex')` возвращает 10 моделей.
- После рестарта Dashboard API возвращает `openai-codex.total_models = 10`.

## Root cause
1. Запущенный Dashboard держал старый импортированный каталог Codex моделей: 7 entries.
2. `codex_models.get_codex_model_ids(access_token=...)` раньше заменял curated список live-ответом API. Live endpoint ChatGPT сейчас отдаёт 7 записей, из них часть фильтруется (`supported_in_api=false`, `visibility=hide`), поэтому compatibility/hidden slugs из config не попадали в picker.
3. `list_authenticated_providers()` раньше мог отдать built-in/overlay row раньше, чем `providers.openai-codex` из `config.yaml`, поэтому явный список из config мог быть затенён.

## Изменения
- `hermes_cli/codex_models.py`:
  - `DEFAULT_CODEX_MODELS` расширен до 10 рабочих моделей;
  - live API discovery теперь merge'ится с curated defaults, а не заменяет их.
- `hermes_cli/model_switch.py`:
  - `openai-codex` берётся через `provider_model_ids()`;
  - built-in provider rows merge'ят явные `providers.<slug>.models` из `config.yaml`, чтобы config не затенялся overlay/built-in строкой.
- `tests/hermes_cli/test_codex_models.py` и `tests/hermes_cli/test_model_switch_custom_providers.py`:
  - добавлены regression assertions на live+curated merge и сохранение config models.

## Verification
- Direct Python runtime:
  - `config models`: 10
  - `provider_model_ids('openai-codex')`: 10
  - `list_authenticated_providers(... openai-codex ...)`: `total_models=10`
- Dashboard restarted:
  - old PID `2126339` stopped;
  - new PID `2127765` running `hermes dashboard --host 0.0.0.0 --port 9119 --insecure --no-open`.
- Dashboard API after restart:
  - `openai-codex.total_models = 10`
  - models: `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.3-codex`, `gpt-5.2`, `gpt-5.1-codex-max`, `gpt-5.1-codex-mini`, `gpt-5.2-codex`, `gpt-5-codex`, `codex-auto-review`.

## Notes
- Browser automation could not be used for visual UI verification in this environment because Chromium failed to start without `--no-sandbox`; API is the UI data source for the model picker.
- No secrets/tokens were printed or edited.
