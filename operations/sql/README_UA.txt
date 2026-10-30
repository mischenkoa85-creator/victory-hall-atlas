СКЛАД — ПЕРШИЙ ВЕРТИКАЛЬНИЙ ЗРІЗ, ЛОКАЛЬНИЙ КАНДИДАТ

001_warehouse_candidate.sql НЕ застосовано до VPS/production. Немає номера live-міграції,
реальних залишків, реальних capability grants або нових SQL-ролей.

Що реалізовано
- Номенклатура та місця зберігання, окремі від встановлених активів 3D-моделі.
- Права warehouse.read/catalog/opening/receipt/issue/transfer/reverse окремо для
  користувача та об'єкта; location_id NULL означає всю установу, інакше лише місце.
- Автор і сесія беруться винятково з core._atlas_context, записи вимагають CSRF.
- Нове місце/номенклатура не створює підтверджений нуль: quantity NULL, balance_known=false.
- opening встановлює одноразовий підтверджений залишок (включно з явним нулем).
- receipt додає; issue видає з обов'язковим посиланням на роботу;
  transfer атомарно списує з одного місця та зараховує в інше.
- reversal робить повний зворотний запис receipt/issue/transfer, лише один раз,
  без редагування первинної операції, лише якщо не виникає від'ємного залишку.
- Документ/підстава обов'язкові. Посилання на об'єкт та роботу зберігаються як
  джерельні посилання, а не автоматично підтверджені канонічні зв'язки.
- Кількість NUMERIC(18,3); NaN/Infinity, приховане округлення та мінус заборонені.
- Блокування на номенклатуру/об'єкт і ключ ідемпотентності: дубль не подвоює рух.
- Рух, баланс, незмінний ledger і core._atlas_audit в одній транзакції.
- Перегляд дозволених місць, залишків і журналу з обмеженою пагінацією.

Чого ще НЕ реалізовано
- Резервування/звільнення резерву; кількість не називається «доступно до видачі
  після резервів». Резерви не вважаються нульовими фактичними даними.
- Часткові повернення, довільне коригування/списання, корекція opening.
- Ціни, собівартість, закупівлі, відповідальні за місця, внутрішні погодження.
- Файлове сховище фото/документів, підтвердження існування work/object references.
- API, сторінки Атласу, серверна міграція й приймання власником.

Інтерфейс для BFF
У транзакції, як SQLSessionRepository._request, спочатку core.atlas_begin_request
із захищеної серверної сесії. Далі один із fixed SQL викликів, COMMIT перед успіхом:
atlas_ops.warehouse_location_list(facility_uuid)
atlas_ops.warehouse_stock_list(facility_uuid, location_uuid)
atlas_ops.warehouse_history(facility_uuid, location_uuid, before_entry_id, limit)
atlas_ops.warehouse_put_item(facility_uuid,item_uuid,label,unit,kind)
atlas_ops.warehouse_put_location(facility_uuid,location_uuid,label)
atlas_ops.warehouse_post(facility_uuid,idempotency_key,kind,item_uuid,quantity,
 from_location,to_location,document_reference,reason,work_reference,object_reference,reference_operation)
Для reversal quantity/from/to=NULL, reference_operation — первинна операція.
Передавання actor_id, email, ролі або повноважень із HTTP не передбачено.

Помилки SQL: 42501 — scope/CSRF/context denied; 28000 — нечинна сесія;
22023 — бізнес-помилка (unknown opening, insufficient stock, idempotency conflict,
already reversed, invalid precision etc). Тексти SQL не повертати напряму клієнту.
Технічний збій і невідомий COMMIT не означають успіх: повтор з тим самим ключем.

Розгортання потребує root-review, нового схваленого пакета міграції/backup/rehearsal,
прив'язки facility до чинного реєстру та окремого призначення реальних capabilities.
Загальний board/read доступ не надає прав warehouse.*.

Тест: operations/tests/test_warehouse_pg.py створює лише НОВИЙ локальний кластер PG17
на 127.0.0.1, відтворює фактичний 01_session_core.sql із синтетичними особами і
зупиняє кластер у finally. Усі попередні локальні та серверні БД залишаються незмінними.
