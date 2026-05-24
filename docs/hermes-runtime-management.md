# Hermes Runtime Management

Дата: 2026-05-12. Статус: legacy/release-dir. На 2026-05-24 release-dir рассматривается как временная схема; целевая архитектура — supported pip venv. См. актуальный runbook: `docs/hermes-release-dir-to-pip-migration.md`.

## Общая схема

Hermes работает на **host runtime** через `systemd --user`, не в Docker.

Активный runtime — **release-dir**: симлинк `/home/konstantin/.hermes/hermes-agent` → конкретный релиз в `/home/konstantin/.hermes/releases/`.

```
/home/konstantin/.hermes/hermes-agent          ← активный symlink
  → /home/konstantin/.hermes/releases/hermes-agent-d04c50f2f614   ← текущий production release на 2026-05-24
      ├── venv/
      ├── run_agent.py
      ├── hermes_cli/
      ├── gateway/
      ├── tools/
      └── scripts/
```

systemd запускает:
```
/home/konstantin/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main gateway run
```
Путь через symlink ведёт в release directory. Это нормально.

## Текущий активный релиз

- **Release:** `hermes-agent-d04c50f2f614`
- **Путь:** `/home/konstantin/.hermes/releases/hermes-agent-d04c50f2f614`
- **Старый backup:** `/home/konstantin/.hermes/hermes-agent.pre_r12a_messagingfix_20260512051431`

Проверить текущий runtime:
```bash
readlink -f /home/konstantin/.hermes/hermes-agent
# Ожидаемо: /home/konstantin/.hermes/releases/hermes-agent-d04c50f2f614
```

Убедиться, что не Docker:
```bash
docker ps   # должен быть пуст или не содержать hermes
ps aux | grep -E '[h]ermes|[p]ython.*hermes_cli'
```

## Управление сервисом

### Перезапуск
```bash
systemctl --user restart hermes-gateway
```

### Проверка статуса
```bash
systemctl --user is-active hermes-gateway
systemctl --user status hermes-gateway --no-pager -n 40
```

### Логи
```bash
# Обычные
journalctl --user -u hermes-gateway -n 100 --no-pager

# Только ошибки
journalctl --user -u hermes-gateway -n 200 --no-pager \
  | grep -Ei "error|exception|traceback|ImportError|503|file is not a database"
```

Перезапуск **не** сбрасывает release — symlink остаётся тем же.

## Обновление Hermes (правильный процесс)

1. Работать в git-репозитории.
2. Commit.
3. Docker sandbox smoke test.
4. Создать release dir: `/home/konstantin/.hermes/releases/hermes-agent-<commit>`.
5. Установить venv и зависимости.
6. Проверить import/help/smoke.
7. `systemctl --user stop hermes-gateway`.
8. Переключить symlink: `ln -sfn /home/konstantin/.hermes/releases/hermes-agent-<commit> /home/konstantin/.hermes/hermes-agent`.
9. `systemctl --user start hermes-gateway`.
10. Проверить: Telegram `/reset` + `ping`.
11. Только потом включать новые flags/config.

### Чего НЕ делать

- ❌ `cp run_agent.py` в production
- ❌ `cp budget_config.py` в production
- ❌ Править venv руками
- ❌ Symlink на `/tmp`
- ❌ Deploy без smoke
- ❌ Редактировать файлы внутри активного release dir

Активный release считается **immutable**. Нужны изменения → новый release.

## Откат только compaction (мягкий rollback)

Выключить feature flag, не трогая runtime:

```yaml
# ~/.hermes/config.yaml
tool_output_compaction:
  enabled: false
```

```bash
systemctl --user restart hermes-gateway
```

Применять если:
- Telegram отвечает странно;
- Большой terminal output пропадает или ломается;
- Artifacts пишутся не туда;
- Подозрение на утечку raw/secret;
- Новые ошибки в gateway.

## Полный откат runtime на старый Hermes

1. `systemctl --user stop hermes-gateway`
2. Переключить symlink обратно на старую директорию:
   ```bash
   ln -sfn /home/konstantin/.hermes/hermes-agent.pre_r12a_messagingfix_20260512051431 /home/konstantin/.hermes/hermes-agent
   ```
3. `systemctl --user start hermes-gateway`
4. Проверить.

Откат — это **переключение symlink**, не копирование файлов.

## Tool Output Compaction

### Текущая конфигурация

```yaml
tool_output_compaction:
  enabled: true
  rollout_platforms: [telegram]
  enabled_output_kinds: [terminal]
  artifact_root: /tmp/hermes-tool-output-compaction-artifacts
  secret_policy: redact_or_block
```

Compaction применяется **только** к `terminal` output через Telegram.

Не применяется к: `file_read`, `search`, `web`, обычным сообщениям, `ContextCompressor`.

### Artifacts

- **Root:** `/tmp/hermes-tool-output-compaction-artifacts`
- **Пример:** `/tmp/hermes-tool-output-compaction-artifacts/20260512_051610_4df1d79e/msg_0004_call_oy3zesei.raw`

⚠️ `/tmp` может очищаться системой. Для временного режима это нормально. Для постоянного хранения перенести root, например, в `/home/konstantin/.hermes/tool-output-artifacts` — но не сейчас, подождать 1–2 дня эксплуатации.

### Принцип работы

- Длинный terminal output → в контекст попадает compacted summary.
- Полный raw output сохраняется в artifact.
- Короткий output может пройти без compaction.
- Строки, похожие на секреты → block/redact.

## Мониторинг

Мониторить не «всё подряд», а **5 признаков**:

1. Hermes отвечает в Telegram.
2. Gateway не падает.
3. Нет свежих критических ошибок.
4. Compaction реально срабатывает на больших terminal outputs.
5. Artifacts пишутся только в нужный каталог.

### Быстрая ручная проверка

**1. Проверить active runtime**

```bash
readlink -f /home/konstantin/.hermes/hermes-agent
```
Ожидаемо: `/home/konstantin/.hermes/releases/hermes-agent-d04c50f2f614`

**2. Проверить gateway**

```bash
systemctl --user is-active hermes-gateway    # → active
systemctl --user status hermes-gateway --no-pager -n 40   # подробно
```

**3. Проверить свежие ошибки**

```bash
journalctl --user -u hermes-gateway --since "30 minutes ago" --no-pager \
  | grep -Ei "ImportError|ModuleNotFoundError|traceback|exception|file is not a database|503|server overloaded|ToolOutputCompactionConfig|No adapter available|python-telegram-bot" \
  || true
```

Ожидаемо: **пусто**.

Расшифровка:
- `503` → обычно проблема provider/model route
- `ImportError` / `ModuleNotFoundError` → проблема runtime/release
- `file is not a database` → проблема memory DB

**4. Проверить, что compaction включена**

```bash
grep -nA12 "tool_output_compaction" ~/.hermes/config.yaml
```

Ожидаемо:
```yaml
tool_output_compaction:
  enabled: true
  rollout_platforms: [telegram]
  enabled_output_kinds: [terminal]
  artifact_root: /tmp/hermes-tool-output-compaction-artifacts
  secret_policy: redact_or_block
```

**5. Проверить artifacts**

До теста:
```bash
find /tmp/hermes-tool-output-compaction-artifacts -maxdepth 4 -type f | wc -l
```

Последние:
```bash
find /tmp/hermes-tool-output-compaction-artifacts -maxdepth 4 -type f \
  -printf '%TY-%Tm-%Td %TH:%TM %s %p\n' | sort | tail -20
```

Тест: в Telegram попросить Hermes выполнить команду с большим synthetic output (без секретов):
```bash
python - <<'PY'
for i in range(180):
    print(f"MONITOR_COMPACTION_LINE_{i:03d} " + "x" * 160)
PY
```

После выполнения → снова проверить artifacts. Ожидаемо:
- появился новый `.raw` artifact;
- в Telegram вернулся **summary**, а не все 180 строк;
- в логах нет критических ошибок.

### Один удобный monitoring script

```bash
echo "== runtime =="
readlink -f /home/konstantin/.hermes/hermes-agent

echo "== gateway =="
systemctl --user is-active hermes-gateway

echo "== compaction config =="
grep -nA12 "tool_output_compaction" ~/.hermes/config.yaml || true

echo "== latest artifacts =="
find /tmp/hermes-tool-output-compaction-artifacts -maxdepth 4 -type f \
  -printf '%TY-%Tm-%Td %TH:%TM %s %p\n' 2>/dev/null | sort | tail -10

echo "== recent critical logs =="
journalctl --user -u hermes-gateway --since "30 minutes ago" --no-pager \
  | grep -Ei "ImportError|ModuleNotFoundError|traceback|exception|file is not a database|503|server overloaded|ToolOutputCompactionConfig|No adapter available|python-telegram-bot" \
  || true
```

### Как понять, что всё работает правильно

**Норма:**
- gateway: `active`
- active runtime: `/home/konstantin/.hermes/releases/hermes-agent-d1c549c4`
- `tool_output_compaction.enabled: true`
- `rollout_platforms: [telegram]`
- `enabled_output_kinds: [terminal]`
- новые `.raw` artifacts появляются после больших terminal outputs
- Telegram получает summary, не полный огромный stdout
- свежих `ImportError`/`503`/traceback нет

**Плохо:**
- gateway `inactive`
- Telegram не отвечает
- новый большой terminal output вернулся целиком (без compaction)
- artifact не появился
- artifact появился вне `/tmp/hermes-tool-output-compaction-artifacts`
- есть `ImportError` / `ToolOutputCompactionConfig` / `file is not a database`
- `503` появляется на маленьком ping

### Если что-то пошло не так

Самый мягкий rollback — выключить compaction, не трогая runtime:

```yaml
# ~/.hermes/config.yaml
tool_output_compaction:
  enabled: false
```

```bash
systemctl --user restart hermes-gateway
```

Это отключит compaction, но оставит новый release runtime активным.

## Почему release-dir, а не копирование файлов в живую директорию

Прошлая попытка: файлы копировались частями в живую production-директорию → mixed runtime (`run_agent.py` новый, `budget_config.py` старый) → `ImportError: cannot import ToolOutputCompactionConfig`.

Release-dir устраняет это: каждый релиз — полный согласованный набор файлов. Обновление = атомарное переключение symlink.

## Push на GitHub

Локальные commits не pushed. Перед push:
1. Решить: пушить ли ветку `context-input-baseline`.
2. Все ли commits нужны.
3. Нет ли секретов, logs, artifacts в истории.
4. Пусть агент сделает audit: `git log`, `git status`, `git diff origin/<branch>...HEAD --stat`, secret scan.