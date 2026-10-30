КОМАНДИ: ПЕРЕВІРИТИ РЕЗУЛЬТАТ АБО СКАСУВАТИ, ЯКЩО НЕ ЗБЕРЕЖЕНО

Це локальний кандидат; Linux SQL/HTTP перевірка цієї нової дельти ще не виконана.
Foundation command_resolution і private guards визначені в001, щоб усі writer
функції від самого початку брали участь у протоколі. Публічний resolver — SQL005.

POST /v1/session/operations/{facility_id}/commands/resolve
Cookie + Origin + X-CSRF-Token, JSON тільки {domain,key}.
domain: warehouse, board, attachment, item, location, category.
key: точний ключ writer. Для item/location/category — canonical client UUID.
Actor завжди з перевіреного core._atlas_context; actor/email/роль із HTTP заборонені.

Відповідь200 (після COMMIT):
{data:{status:"COMMITTED",domain:"...",key:"...",receipt:<первинне data writer>}}
або {data:{status:"CANCELLED",domain:"...",key:"...",receipt:null}}.
Це активне скасування за явною командою користувача, не GET-перевірка тайм-ауту.

Resolver і writer беруть ТОЙ САМИЙ advisory lock:
domain + ':key:' + facility + ':' + verified_actor + ':' + key.
Уже проведена команда повертає первинну квитанцію після повторної перевірки
доступу до цільового місця/заявки. Для catalog знову перевіряються відповідні права.
Якщо власного запису немає, resolver із чинним правом дії в цьому об'єкті записує
immutable CANCELLED + audit. Запізнілий writer бачить tombstone під цим самим lock
і відхиляється409 COMMAND_CANCELLED. Повторний resolver повертає той самий outcome.

Namespace включає actor/facility: інший користувач ніколи не отримує чужу receipt.
Існування того самого key в іншому namespace взагалі не перевіряється.
Для неіснуючої власної команди дозволений caller може скасувати лише свій key.
Недостатні права на об'єкт →403, не створення tombstone для чужого об'єкта.

Catalog не вважає існуючий рядок доказом успіху поточної людини: потрібна власна
command receipt. Чужий existing item/location/category дає conflict без власного
COMMITTED. Усі catalog insert і receipt, ledger/report/outbox та audit атомарні.

Порядок блокувань board: writer/verifier task→command key; resolver command key
→просте MVCC читання scope без task row lock. Це усуває цикл взаємних очікувань.
Attachments беруть key у preflight ДО запису файла. Фото може вже бути збережене,
коли користувач скасовує фінальну board-команду завершення: фото лишається в історії,
а виконання роботи не вигадується. Команди attachment і board мають різні ключі.

Клієнт може зберігати мінімальний marker {userId,facility,domain,key,mode}, без
payload, фото або токенів. Для composition upload→completion фінальний marker
від початку вказує board key. Після reload payload не потрібен для resolver.

Тести: portable runner --resolution-check (включає необхідні board/attachment/
workspace SQL); результат COMMAND_RESOLUTION_RESULT.json. Є completed readback,
cancelled delayed writes, actor/facility separation, audit rollback, catalog proof,
photo-before-cancel, concurrency writer-first/resolver-first та MVCC task scope.
Жодних БД чи служб цей текст/файли самі не оновлюють.

Перед міграцією в БД, де вже могли виконуватися старі writer-функції БЕЗ foundation,
потрібен окремий перевірений backfill власних receipt. Без нього resolver не можна
активувати для legacy command keys. Поточні модулі ще candidate, тестові БД нові.
