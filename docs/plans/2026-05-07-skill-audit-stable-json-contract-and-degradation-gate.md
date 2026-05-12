# Skill audit stable JSON contract and degradation gate

Source: `/home/konstantin/.hermes/cache/documents/doc_bb84587f51fd_contract.txt`

Purpose: preserve the contract/design note for future implementation of `skill-audit-and-improvement` and `audit_skill.py` as a deterministic quality gate.

---

TL;DR:
Stable JSON report не надо внедрять в каждый skill как отдельный артефакт. Его надо внедрить как единый контракт audit_skill.py.
CLI не нужен каждому skill. CLI нужен только тем skills, где есть повторяемая исполняемая логика, live checks, redaction, JSON-контракт или интеграция с CI.
Чтобы заблокировать деградацию skills, нужен связанный контур: schema → audit_skill → CI required check → branch protection → baseline/no-regression policy → blocker-only review.

⸻

1. Вывод после поиска и повторного анализа

Внешние практики подтверждают не идею «каждый компонент обязан иметь свой JSON», а идею стабильного машинного контракта там, где результат потребляет машина. JSON Schema официально позиционируется как способ описывать структуру, ограничения и типы JSON-данных, а также поддерживать автоматическую валидацию и machine/human-readable documentation. Поэтому JSON-контракт логично ставить на границе audit_skill.py, а не размазывать по каждому SKILL.md.  

Для CLI вывод похожий: CLI Guidelines рекомендуют корректные exit codes, machine-readable output в stdout и human/error messages в stderr; GitHub CLI использует --json как режим, который превращает вывод команды в JSON и позволяет дальше фильтровать его через jq/template. Это аргумент за --json у инструментов, но не за обязательный CLI в каждом skill.  

Для блокировки деградации ключевой слой — не локальный скрипт, а enforced gate. GitHub branch protection позволяет требовать status checks перед merge, а required status checks должны пройти до merge в protected branch. CI, в свою очередь, как раз предназначен для запуска tests, linters, security checks и custom checks при изменениях.  

⸻

2. Стоит ли внедрять Stable JSON report в каждый skill?

Нет, не в каждый skill.

Правильнее так:

1. Каждый skill должен быть machine-auditable.
    То есть SKILL.md, frontmatter, support files, links, scripts, templates и related ownership должны быть проверяемы через audit_skill.py.
2. Каждый audit result должен иметь stable JSON report.
    Это обязанность audit_skill.py, а не каждого skill.
3. Каждый script/CLI внутри skill, который является инструментом, должен иметь stable JSON mode.
    Но только если его результат реально будет использоваться агентом, CI, другим CLI или review automation.

Иначе получится ложная стандартизация: много JSON-оберток без потребителя, много схем без смысла, больше maintenance surface и больше мест, где можно сломать контракт.

⸻

3. Где JSON обязателен, где желателен, где не нужен

Обязателен:

* audit_skill.py --json;
* audit_skill.py --changed --json;
* doctor --json для owning CLI;
* secret/redaction scanners;
* stale path scanners;
* repository-wide skills inventory;
* CI reports;
* blocker-only review output, если review автоматизирован.

Желателен:

* scripts, которые возвращают findings;
* scripts, которые проверяют deterministic conditions;
* scripts, которые используются агентом как evidence source;
* tools, где нужно сравнение baseline vs current.

Не нужен по умолчанию:

* обычный instructional SKILL.md;
* references/*.md;
* templates/*.md;
* короткие one-off helper scripts без downstream consumer;
* skills, которые только описывают процедуру и не исполняют проверки.

⸻

4. Стоит ли внедрять CLI в каждый skill?

Нет. CLI должен быть исключением, а не нормой.

CLI оправдан, если есть хотя бы один из этих признаков:

* workflow повторяется часто;
* есть live checks;
* есть несколько subcommands;
* нужен --json;
* нужна redaction;
* есть сложная диагностика;
* нужен doctor;
* есть CI integration;
* есть stateful или multi-file validation;
* команда должна быть удобной для человека и агента.

Для большинства skills достаточно:

SKILL.md
references/
templates/
scripts/

CLI стоит добавлять только когда scripts/ уже стали неуправляемыми или когда нужен явный tool contract. Это соответствует общей практике CLI: машинный вывод должен быть четко отделен от human output, а exit codes должны быть пригодны для автоматизации.  

⸻

5. Рекомендуемая архитектура

Предпочтительная схема:

skills/
  software-development/
    skill-audit-and-improvement/
      SKILL.md
      schemas/
        audit-report.schema.json
        skill-frontmatter.schema.json
        cli-doctor.schema.json
      scripts/
        audit_skill.py
        validate_audit_report.py
        validate_skill_frontmatter.py
      references/
        audit-rubric.md
        finding-taxonomy.md
        degradation-policy.md
      templates/
        final-report.md
        blocker-review.md

Не надо класть audit-report.schema.json внутрь каждого skill.
Схема должна жить у владельца проверки: skill-audit-and-improvement.

⸻

6. Минимальный stable JSON contract для audit_skill.py

Я бы зафиксировал такую структуру:

{
  "schema_version": "1.0.0",
  "tool": {
    "name": "audit_skill",
    "version": "0.1.0"
  },
  "repo": {
    "root": "...",
    "branch": "...",
    "commit": "...",
    "dirty": true
  },
  "target": {
    "skill": "skill-audit-and-improvement",
    "path": "skills/software-development/skill-audit-and-improvement",
    "mode": "single"
  },
  "summary": {
    "blockers": 0,
    "warnings": 2,
    "recommendations": 4,
    "score": 92
  },
  "findings": [
    {
      "rule_id": "STALE_PATH",
      "severity": "blocker",
      "category": "source_runtime_correctness",
      "message": "Referenced path does not exist",
      "location": {
        "path": "SKILL.md",
        "line": 42,
        "column": 7
      },
      "evidence": {
        "kind": "path",
        "value": "scripts/old_checker.py",
        "redacted": false
      },
      "suggested_fix": "Update or remove the stale path reference",
      "fingerprint": "..."
    }
  ],
  "checks": [
    {
      "rule_id": "FRONTMATTER_VALID",
      "status": "pass"
    }
  ],
  "evidence_manifest": [
    {
      "path": "SKILL.md",
      "kind": "primary"
    }
  ]
}

Версионирование схемы нужно вести как публичный контракт: breaking changes — major, backward-compatible additions — minor, bug fixes — patch. Это близко к SemVer-логике: сначала нужно явно определить public API, затем версионировать изменения в зависимости от совместимости.  

⸻

7. Предпочтительный порядок внедрения

Этап 1 — зафиксировать единый контракт аудита

Сначала создать:

schemas/audit-report.schema.json
schemas/skill-frontmatter.schema.json
references/finding-taxonomy.md
references/degradation-policy.md

Цель: audit_skill.py --json должен быть не просто красивым выводом, а стабильным интерфейсом.

Обязательные поля:

* schema_version;
* tool;
* repo;
* target;
* summary;
* findings;
* checks;
* evidence_manifest.

⸻

Этап 2 — встроить self-validation в audit_skill.py

audit_skill.py должен валидировать собственный JSON перед выводом:

python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py \
  --skill skill-audit-and-improvement \
  --json

Затем:

python3 skills/software-development/skill-audit-and-improvement/scripts/validate_audit_report.py \
  /tmp/audit-report.json

Можно использовать Python jsonschema: библиотека реализует JSON Schema validation, а validate() проверяет instance against schema.  

⸻

Этап 3 — добавить --changed

Это главный режим для CI:

python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py \
  --changed \
  --json

Он должен учитывать:

git diff --name-only
git diff --name-only --cached
git ls-files --others --exclude-standard

И группировать изменения по:

skills/<category>/<skill>/

⸻

Этап 4 — ввести exit codes

Рекомендую:

0 = no blockers
1 = blockers found
2 = invalid invocation / repo error / schema error
3 = internal audit failure

Это важно для CI и shell automation. CLI Guidelines прямо рекомендуют zero exit code on success и non-zero on failure, потому что scripts используют exit codes для определения результата.  

⸻

Этап 5 — добавить локальный pre-commit, но не полагаться только на него

Pre-commit полезен как ранний фильтр: он запускает hooks перед commit и помогает отлавливать простые проблемы до code review.  

Минимальный .pre-commit-config.yaml:

repos:
  - repo: local
    hooks:
      - id: audit-changed-skills
        name: audit changed skills
        entry: python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --changed --json
        language: system
        pass_filenames: false
      - id: git-diff-check
        name: git diff check
        entry: git diff --check
        language: system
        pass_filenames: false

Но pre-commit — не финальная защита. Git hooks можно обходить локально; поэтому деградацию нужно блокировать в CI и branch protection.

⸻

Этап 6 — сделать GitHub Actions required check

Пример workflow:

name: skills-quality-gate
on:
  pull_request:
  push:
    branches: [main]
jobs:
  audit-skills:
    name: audit-skills
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Git diff check
        run: git diff --check
      - name: Audit changed skills
        run: |
          python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py \
            --changed \
            --json \
            --output /tmp/audit-report.json
      - name: Validate audit JSON schema
        run: |
          python3 skills/software-development/skill-audit-and-improvement/scripts/validate_audit_report.py \
            /tmp/audit-report.json

CI должен запускать tests, linters, security checks и custom checks при изменениях; GitHub Actions прямо описывает такую модель continuous integration.  

⸻

Этап 7 — включить branch protection

На main:

Require pull request before merging
Require status checks before merging
Required check: audit-skills
Require branches to be up to date before merging
Require review from code owners
Dismiss stale approvals
Do not allow bypassing
Disable force pushes
Disable deletions

GitHub branch protection позволяет требовать status checks, reviews, linear history и другие условия перед merge. Required status checks должны пройти перед merge в protected branch.  

Важно: required job не должен быть условно skipped. GitHub docs отдельно указывают, что skipped job может отображаться как success и не блокировать PR даже как required check. Поэтому audit-skills должен запускаться всегда, а внутри сам решать, есть ли changed skills.  

⸻

Этап 8 — добавить baseline/no-regression policy

После первого полного аудита сохранить baseline:

.skills-audit-baseline.json

Дальше CI должен блокировать:

new blocker
new secret-like finding
new stale path
new unsafe command
frontmatter invalid
schema invalid
audit script failed
score decreased below threshold
warning count increased above allowed budget

Не обязательно сразу блокировать все старые warnings. Лучше:

existing warnings = allowed temporarily
new warnings = blocked or require review
blockers = always blocked

Это критично: иначе первый запуск аудита может дать слишком много старого шума, и gate выключат.

⸻

Этап 9 — добавить SARIF только после стабильного JSON

Не надо начинать с SARIF. Сначала internal JSON.
Потом можно добавить:

audit_skill.py --changed --sarif > /tmp/skills-audit.sarif

SARIF полезен, если хочется видеть findings как code scanning alerts в GitHub. SARIF — стандартный формат для результатов static analysis, а GitHub поддерживает загрузку SARIF 2.1.0 subset для code scanning.  

⸻

Этап 10 — CLI только для зрелых workflow

После того как audit_skill.py стабилен, можно делать owning CLI:

skills-audit audit --changed --json
skills-audit audit --skill <name> --json
skills-audit doctor --json
skills-audit schema validate /tmp/report.json
skills-audit baseline compare --current /tmp/report.json

Но это должен быть CLI одного владельца — skill-audit-and-improvement, а не CLI в каждом skill.

⸻

8. Как именно валидировать через audit_skill.py

Для одиночного skill:

git diff --check
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py \
  --skill <skill-name> \
  --json \
  --output /tmp/audit-skill.json
python3 skills/software-development/skill-audit-and-improvement/scripts/validate_audit_report.py \
  /tmp/audit-skill.json

Для всех измененных skills:

git diff --check
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py \
  --changed \
  --json \
  --output /tmp/audit-changed.json
python3 skills/software-development/skill-audit-and-improvement/scripts/validate_audit_report.py \
  /tmp/audit-changed.json

Для Python-файлов:

PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile <changed_python_file>

Или лучше через AST parse, если нужно гарантированно не создавать bytecode.

Для CLI внутри skill:

<cli> --help
<cli> doctor --json > /tmp/doctor.json
python3 skills/software-development/skill-audit-and-improvement/scripts/validate_cli_doctor.py \
  /tmp/doctor.json

⸻

9. Как заблокировать деградацию skills

Нужны 7 уровней защиты.

1. Stable rule IDs

Каждая проверка должна иметь постоянный rule_id:

FRONTMATTER_INVALID
MISSING_TRIGGER
MISSING_WHEN_NOT_TO_USE
STALE_PATH
SECRET_LIKE_VALUE
UNSAFE_GREP_SECRET
BROKEN_MARKDOWN_LINK
SCRIPT_SYNTAX_ERROR
CLI_JSON_INVALID
MISSING_VERIFICATION
DUPLICATE_SKILL_OWNER
SELF_AUDIT_RECURSION_RISK

Без стабильных rule IDs невозможно baseline-сравнение.

⸻

2. Fingerprints для findings

Каждый finding должен иметь fingerprint:

hash(rule_id + normalized_path + normalized_evidence)

Это позволяет отличать:

старую проблему
новую проблему
исправленную проблему
изменившуюся проблему

⸻

3. Baseline compare

Политика:

block if new blocker
block if new secret-like issue
block if new stale path
block if JSON schema invalid
block if audit failed
warn if new recommendation
allow known old warnings temporarily

⸻

4. Required CI check

audit-skills должен быть required status check. GitHub protected branches могут требовать прохождения status checks до merge, и без этого локальные проверки легко обходятся.  

⸻

5. CODEOWNERS и blocker-only review

Для критичных зон:

skills/software-development/skill-audit-and-improvement/**
skills/**/scripts/**
skills/**/cli/**
.skills-audit-baseline.json
.github/workflows/skills-quality-gate.yml

Нужен обязательный review от владельца skills architecture.

Review должен быть blocker-only:

- stale paths?
- secrets?
- unsafe commands?
- invalid frontmatter?
- broken CLI JSON?
- missing verification?
- duplicate skill ownership?
- audit bypass?

⸻

6. Negative test fixtures

Нужно создать искусственно сломанные skills:

tests/fixtures/skills/invalid-frontmatter/
tests/fixtures/skills/stale-path/
tests/fixtures/skills/secret-like/
tests/fixtures/skills/unsafe-command/
tests/fixtures/skills/missing-triggers/
tests/fixtures/skills/duplicate-owner/

И тестировать, что audit_skill.py реально ловит деградацию.

Это важнее, чем просто тестировать happy path.

⸻

7. Policy-as-code, когда правил станет много

Если правил станет много и они будут больше похожи на governance, чем на Python checks, можно вынести часть в policy-as-code. OPA прямо описывает использование policy-as-code guardrails в CI/CD для validation outputs и enforcement organizational policies before code reaches production; Conftest предназначен для тестирования structured configuration data.  

На раннем этапе OPA/Conftest не обязательны. Сначала достаточно Python + JSON Schema + CI.

⸻

10. Что именно блокировать как деградацию

Blocker:

invalid SKILL.md frontmatter
missing SKILL.md
stale path in executable instruction
secret-like value without redaction
unsafe command that can print secrets
script syntax error
CLI --json invalid
audit report schema invalid
audit script modifies repo
new duplicate skill owner
self-audit recursion not guarded

Warning:

missing when-not-to-use
weak triggers
no rollback guidance
no verification section
long SKILL.md should move case to references/
template embedded in SKILL.md
support file orphaned
related skills not referenced

Recommendation:

add template
add reference case
add deterministic script
add CLI only if repeated live workflow exists
add SARIF output after JSON is stable

⸻

11. Практическая политика внедрения

Я бы ввел так:

Week 1:
- audit-report.schema.json
- stable audit_skill.py --json
- validate_audit_report.py
- rule_id taxonomy
Week 2:
- --changed
- baseline file
- new blocker detection
- git diff --check
- Python syntax checks
Week 3:
- GitHub Actions required check
- branch protection
- CODEOWNERS
- blocker-only review template
Week 4:
- negative fixtures
- no-regression tests
- secret redaction tests
- stale path tests
Later:
- SARIF output
- owning CLI
- policy-as-code if rules outgrow Python

⸻

12. Конечная рекомендация

Внедряй не «stable JSON в каждый skill», а единый stable audit protocol для всей skills-библиотеки.

Итоговая целевая модель:

Every skill:
- valid frontmatter
- clear triggers
- clear boundaries
- no stale paths
- no secret leakage
- verification guidance
- audit-readable structure
Every audit:
- stable JSON report
- JSON Schema validation
- deterministic exit codes
- evidence manifest
- redacted findings
- baseline comparison
Every CLI:
- only where justified
- --help
- --json
- doctor --json
- stable exit codes
- schema-valid output
Every merge:
- audit_skill.py --changed --json
- schema validation
- baseline/no-regression check
- required CI status
- protected branch
- blocker-only review for risky changes

Самый важный принцип: деградация должна становиться невозможной не потому, что агент “помнит правила”, а потому что repo не принимает изменение, которое нарушает правила.