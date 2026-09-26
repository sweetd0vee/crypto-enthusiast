# Оставшиеся шаги до production

Текущий локальный MVP и его проверки описаны в
[стеке](06-stack.md). Здесь перечислены только ещё не реализованные задачи.
Порядок отражает зависимости: сначала сохранность голосов, затем безопасность
и наблюдаемость, после этого нагрузка и production-деплой.

## P0. Durable-журнал и сверка

Текущий Lua-скрипт атомарно обновляет дедуп и счётчик, но
`VOTE_ASYNC=true` использует очередь процесса.

1. Создать Redis Stream голосов и consumer group.
2. Добавлять событие в stream в той же атомарной операции, что dedup и
   `HINCRBY`.
3. Сохранять batch в PostgreSQL с идемпотентностью
   `(question_id, dedup_key)`.
4. Подтверждать stream message только после успешного commit.
5. Восстанавливать pending messages после рестарта consumer.
6. Ограничить retry и переносить неисправимые события в dead-letter stream.
7. Добавить reconciliation:
   `Redis counters ↔ vote journal ↔ question_result`.
8. Покрыть остановку API, consumer, Redis и PostgreSQL fault-injection
   тестами.

**Готово, когда:** подтверждённый голос переживает одиночный отказ процесса,
а повторная доставка не увеличивает результат.

## P1. Retention и финализация результата

1. Зафиксировать TTL дедупа, live-счётчиков, streams и dead-letter данных.
2. Ввести состояния результата `live`, `finalizing`, `final`.
3. После окна дождаться обработки stream, выполнить сверку и сохранить
   финальный снимок.
4. Запретить автоматический тяжёлый rebuild во время live-окна.
5. Добавить безопасную повторную финализацию и административный retry.
6. Описать срок хранения журнала и удаление старых партиций.

**Готово, когда:** закрытый результат имеет однозначный признак завершения и
воспроизводимо восстанавливается.

## P2. Безопасность

1. Заменить production Bearer-токен на OIDC/OAuth2 с ролями `viewer` и
   `editor`; локальный токен оставить только dev-режиму.
2. Хранить секреты в secret manager и настроить ротацию.
3. В production включить `Secure` cookie, HSTS, CSP,
   `X-Content-Type-Options` и `Referrer-Policy`.
4. Доверять forwarded headers только известному ingress.
5. Исключить токены, cookie, IP и хеши из логов.
6. Добавить ограничение тела запроса и мягкий rate limit по IP/ASN, не
   используя IP как идентификатор голоса.
7. Проверять зависимости, контейнеры и SBOM в CI.

**Готово, когда:** доступ администратора можно отозвать без деплоя, а
автоматическая security-проверка не находит критических проблем.

## P3. Наблюдаемость

1. Структурированные JSON-логи с `request_id`, `question_id`, outcome и
   latency без идентификатора зрителя.
2. Prometheus-метрики:
   - RPS и p50/p95/p99;
   - accepted, duplicate и rejected votes;
   - ошибки и latency Redis/PostgreSQL;
   - глубина и возраст stream/pending;
   - расхождение reconciliation.
3. OpenTelemetry traces для API → Redis → consumer → PostgreSQL.
4. Dashboard и burn-rate alerts.
5. SLO:
   - доступность голосования во время эфира ≥ 99,95%;
   - p99 принятия голоса ≤ 300 мс;
   - потеря подтверждённых голосов = 0;
   - финализация результата ≤ 5 минут.
6. Runbook для отказа Redis, PostgreSQL, consumer и сверки результатов.

**Готово, когда:** учебный инцидент обнаруживается alert и устраняется по
runbook без чтения исходного кода.

## P4. Административный продукт

1. Серверная пагинация, сортировка и фильтрация списка вопросов.
2. Optimistic locking для одновременной правки.
3. Аудит создания, публикации, отмены и изменения вопроса.
4. Предпросмотр зрительской формы и генерация PNG/SVG QR-кода.
5. Предупреждение о несохранённых изменениях и подтверждение публикации.
6. Экспорт финального результата в CSV и JSON.
7. Accessibility: keyboard navigation, focus trap, screen reader, contrast и
   ширины 320–1440 px.

**Готово, когда:** администратор готовит эфир, получает QR и экспортирует
финальный результат без ручных запросов к API.

## P5. Нагрузочная проверка

1. k6-сценарии: ramp-up, минутный пик, повторы, перекос одного варианта и
   чтение результата одновременно с записью.
2. Baseline одного API и Redis: RPS, p99, CPU, память, сеть и ошибки.
3. Несколько stateless API-реплик за load balancer.
4. Redis Cluster; ключи одной Lua/stream операции должны иметь общий hash
   tag.
5. Отдельные deployment/pool и autoscaling policy для public и admin API.
6. Batch insert/COPY, PgBouncer и обслуживание партиций журнала.
7. Soak, Redis failover и остановка consumer под нагрузкой.
8. Capacity plan с запасом не менее 2× для ожидаемого эфира.

**Готово, когда:** воспроизводимый отчёт фиксирует предел, p99, поведение при
отказе и необходимое число реплик и шардов.

## P6. Production-деплой и восстановление

1. Staging и production через IaC.
2. Immutable images с digest; non-root, read-only filesystem,
   limits/requests и graceful shutdown.
3. Rolling/canary deploy и автоматический rollback.
4. Совместимые миграции по схеме expand → migrate → contract; отдельный тест
   обновления с предыдущего релиза.
5. PostgreSQL PITR и регулярно проверяемый restore.
6. Redis persistence/failover policy.
7. Зафиксированные RPO/RTO и game day: потеря primary, зоны и откат релиза.
8. Multi-region принимать только после явного решения о глобальной
   дедупликации и объединении региональных счётчиков.

**Готово, когда:** deploy, rollback и восстановление выполняются по
автоматизированной процедуре и проверены на staging.

## Порядок ближайших итераций

1. Redis Stream, атомарный `XADD`, consumer и pending recovery.
2. Reconciliation, финализация и retention.
3. OIDC и security hardening.
4. Метрики, SLO, alerts и runbook.
5. Пагинация, QR, аудит и accessibility.
6. k6, Redis Cluster, capacity plan и failover.
7. IaC, backups, canary и game day.

Технологии вводятся только для измеренной задачи. Kafka, Kubernetes и
multi-region не добавляются до появления соответствующего профиля нагрузки и
операционных требований.
