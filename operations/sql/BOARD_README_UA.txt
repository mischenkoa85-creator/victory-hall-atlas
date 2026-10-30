КАБІНЕТ ПРАВЛІННЯ / ЗАЯВКИ — ЛОКАЛЬНИЙ SQL-КАНДИДАТ

002_board_candidate.sql виконується після 001_warehouse_candidate.sql.
Немає production head, реальних категорій, людей, grants або відправлення повідомлень.

Реалізований перший вертикальний зріз
- Категорії робіт із відповідальним адміністратором, правилом приймання й дозволом
  на відкриті заявки. Категорія за замовчуванням забороняє відкриті заявки.
- Окремі capabilities board.read/create/assign/execute/review для об'єкта/категорії.
- Приватна заявка default: читають лише creator/assignee/записаний reviewer,
  кожен додатково повинен мати чинний board.read. Сам board/read не відкриває все.
- Адміністратор категорії фіксується як reviewer при створенні. Зміна налаштувань
  категорії не перепризначає заднім числом reviewer/правило приймання старих заявок.
- Стани new/assigned/in_progress/declined/reported_done/closed.
- Виконавець приймає assigned із необов'язковим орієнтовним строком, змінює ETA або
  відмовляє з поясненням. Чужий працівник не може діяти за нього.
  Якщо ETA заданий, він скінченний і в майбутньому; infinity/-infinity заборонені.
- Завершення потребує посилання на фото та явного підтвердження «Роботу виконав».
  Автор/час/версія звіту беруться із захищеної сесії та БД.
- Прості роботи закриває виконавець при report_done. Інші лишаються reported_done,
  поки записаний reviewer окремо не закриє їх. Самоприймання заборонене.
- Історія подій/звітів незмінна. Idempotency key + optimistic task version.
- Task/report/event/command/core audit/outbox в одній транзакції.
- Outbox для автора та адміністратора — окремі записи навіть для однієї особи.
  Призначення створює повідомлення виконавцю. Dispatcher відсутній: нічого не надсилається.
- Перегляд заявки, дозволеного списку, історії, власної черги повідомлень.
  Усі списки обмежені 1–200 записами на сторінку і мають keyset cursor до старших
  за віком записів; курсор не розширює права. Історія сортується від нових до старих.

НЕ реалізовано цим пакетом
- Договори, кошториси, бухгалтерія/банк, платежі, офіційні голосування, чати/опитування.
- Адмін-інтерфейс категорій/grants, заміна reviewer для існуючих заявок,
  повернення звіту на доопрацювання, редагування/версії вже поданого звіту.
- Доставка push/Telegram/email, вибір каналів та квитанції доставлення.
- Перевірка існування/права доступу до завантаженого фото. photo_reference наразі
  джерельне посилання; attachment service повинен перевіряти його перед production.
- Розгорнутий API/браузерний кабінет та міграція на VPS.

Інтерфейси (лише після core.atlas_begin_request у тій самій транзакції)
board_create(facility,key,category,title,description='',private=true)
board_transition(facility,task,key,expected_version,action,assignee=NULL,eta=NULL,
 reason=NULL,photo=NULL,confirmed=false,photo_sha256=NULL,photo_media_type=NULL)
Останні два параметри — тільки для довіреного серверного attachment verifier;
вони не приймаються в HTTP JSON. Snapshot hash+MIME зберігається у незмінному звіті.
actions: assign, accept, decline, eta, report_done, close.
board_task_get(facility,task)
board_task_list(facility,category,limit=100,before_updated=NULL,before_task=NULL)
board_task_history(facility,task,limit=100,before_version=NULL)
board_notifications(limit=100,before_created=NULL,before_notification=NULL).
board_categories(facility) — лише активні категорії з чинним board.read.
Для наступної сторінки береться timestamp+UUID (або task_version для історії)
останнього запису поточної сторінки. Обидві частини timestamp+UUID передаються
разом. Змінена під час перегляду заявка може переміститися на новішу сторінку;
це оперативний список, не frozen snapshot. Повторне відкриття починається без cursor.
Мутації потребують перевіреного CSRF. actor/role/email із HTTP не приймаються.
API мусить повертати успіх після COMMIT, а бізнес-коди 22023 — через безпечний whitelist.

Тестування: test_warehouse_pg.py --board-check піднімає НОВИЙ ізольований PG17,
спочатку перевіряє склад, потім застосовує цей candidate і запускає board_pg_check.py.
Вхід і context — фактичний session-core; люди/категорії/grants лише синтетичні.

Локальний HTTP-кандидат: operations/board_api.py, attach_board(app,repository,
attachment_verifier=None). Вхід/Origin/CSRF — чинний bff.security, SQL — лише fixed
parameterized calls через SQLSessionRepository. Bool поля strict, ETA — ISO8601
з часовим поясом або NULL. Успішна відповідь лише після COMMIT, SQL22023 — safe409.
Шляхи: /v1/session/board/{facility}/categories; categories/{category}/tasks;
tasks; tasks/{task}; tasks/{task}/history; tasks/{task}/transitions;
сповіщення: /v1/session/board/notifications.

ФОТО: completion failclosed, якщо attachment_verifier не підключений (503).
Текст photo_reference або true не є доказом. Trusted dependency має перевірити
незмінний файл, право чинного користувача й прив'язку facility/task, повернути
VerifiedAttachment із точними user/facility/task/reference, content SHA256 і
дозволеним image MIME. API не завантажує довільні URL і не має default fake verifier.
Реальний attachment store/verifier НЕ реалізовано; без нього production completion
залишається недоступним. SQL зберігає посилання й перевірений сервером hash/MIME
snapshot, але сам не читає файл і не доводить його власність.

--board-http-check у тестовому runner додає actualHTTP/ASGI→actualSQLSessionRepository
→новий PG17. Його synthetic proof registry — лише fixture і не призначений для production.
