# Анализ: не потерялись ли прежние Hermes code patches

Дата: 2026-05-13

Цель: проверить гипотезу, что ранее сделанные кодовые правки Hermes/fact_store/holographic memory были потеряны при release/update/symlink переключениях, и объяснить, почему HRR мог ранее работать, а затем молча деградировать.

План:
1. Собрать evidence из persistent facts/session history про прошлые HRR/fact_store patches.
2. Проверить git provenance: текущий source repo, remotes, branches, commits not-in-upstream, reflog/release metadata.
3. Сравнить ключевые файлы HRR/fact_store/skills/preflight между active release, текущим source HEAD, upstream tag/main и RC.
4. Классифицировать состояние: preserved / pushed / only local dirty / absent from active runtime / likely lost.
5. Дать практический вывод и safe recovery path без production switch.
