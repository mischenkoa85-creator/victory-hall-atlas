ВКЛАДЕННЯ — КАНДИДАТ PRIVATE FILES + SQL METADATA + BFF

003_attachments_candidate.sql застосовується після 002. Немає bytea фото в БД, реальних grants,
публічного файлового маршруту або міграції на VPS.

Файли: attachment_store.py (POSIX), attachment_api.py, requirements-attachments.txt.
Decoder: Pillow 12.3.0 обов'язковий; відсутній decoder означає 503.
JPEG/PNG/WebP, максимум 5 MiB, максимум 20 млн пікселів, один кадр, повні verify і decode.
Оригінальні байти зберігаються без перекодування, із SHA-256 та визначеним decoder MIME.

PrivateAttachmentStore потребує вже створену приватну директорію 0700 під службовим
користувачем ПОЗА web-root. Файли 0600; шляхи за hash генеруються сервером.
POSIX openat/O_NOFOLLOW, exclusive temp, fsync файла, hardlink без перезапису, fsync
директорій. Symlink, неприватні права або пошкоджений існуючий blob відхиляються.
На Windows файловий backend недоступний: небезпечного альтернативного запису немає.

Factory integration (ще НЕ активовано):
 store = PrivateAttachmentStore(private_root)
 attach_attachments(app, repository, store)
 attach_board(app, repository, attachment_verifier=ActualAttachmentVerifier(store))

POST /v1/session/attachments/{facility}/tasks/{task}?purpose=request|completion
 raw image body; Cookie+Origin+X-CSRF-Token, Idempotency-Key, Content-Type.
Потік body обмежується навіть без Content-Length. Multipart, JSON і remote URL не приймаються.
request: лише creator + board.create; completion: лише поточний assignee + board.execute,
стан in_progress. SQL перевіряє scope перед записом файла і перед реєстрацією.
Спочатку приватний blob із fsync, потім metadata + audit COMMIT, лише після нього 200.
SQL failure або невідомий COMMIT не повертає успіх. Може лишитися приватний blob без
metadata; автоматичного видалення/GC немає. Повтор із тим самим ключем і байтами
повертає той самий ідентифікатор вкладення.

GET /v1/session/attachments/{facility}/files/{attachment}
 Чинний task read scope, audit COMMIT і свіжий hash файла перед 200; no-store/private,
nosniff, фіксований Content-Disposition. UUID не є ключем доступу. Пошкодження файла → 503.
GET /v1/session/attachments/{facility}/tasks/{task}
 Список із перевіркою scope, limit 1–200, before_created + before_attachment як курсор.

ActualAttachmentVerifier приймає лише atlas-photo:<canonicalUUID>. SQL перевіряє
actor/facility/task/purpose і стан, filesystem перевіряє свіжий hash/size. Для повторного
completion після закриття допускається лише фото, яке вже записане у тому звіті.
board_report фіксує hash/MIME snapshot. Жодні URL не завантажуються; bool true не є доказом.
Немає demo verifier за замовчуванням; без підключеної залежності board completion → 503.

Тести:
 python -B operations/tests/test_attachment_store.py
 Portable PG runner --attachments-check (POSIX; новий кластер, без чинних БД).
На Windows decoder checks виконуються, POSIX filesystem tests пропускаються.
SQL/HTTP/filesystem integration має виконати root у новому Linux synthetic cluster
перед розгортанням.

Перед production ще потрібні: незалежний review, Linux integration PASS, окрема
приватна постійна директорія та backup/restore, підключення runtime і маршрутів,
обмеження body/rate у сервісі, перевірка фактичного входу і браузера. Orphan blobs,
retention та видалення фото потребують окремої погодженої політики. Доступ до
існуючих приватних фото не розширюється.
