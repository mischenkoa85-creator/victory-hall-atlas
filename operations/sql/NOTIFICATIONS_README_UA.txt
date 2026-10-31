Сповіщення Atlas — кандидат008 та локальні native adapters

Результат
Окремі таблиці preferences/endpoints/jobs/attempts/read markers. board_outbox
залишається незмінною source-подією зі станом pending. Самостійне керування лише
власними налаштуваннями; requested/effective/available відображають різні стани.
Email/Telegram поки недоступні. In-app=false приховує inbox, але не видаляє події.

Безпека й доставка
AES-GCM vault прив’язує ciphertext до facility/user/endpoint через AAD. HMAC
fingerprint закріплює глобальне володіння URL навіть після disable; канонічний
digest підписки робить retry незалежним від нового випадкового ciphertext/nonce.
Сирі endpoint/auth/p256dh/nonce відсутні у SQL command receipts/audit і API errors.
Endpoint записується pending; nonce приходить тільки в шифрованому push, а proof
повертається same-origin authenticated POST+CSRF. Verify/register/enable вимагають
поточних прав; власний status, зменшення каналів і disable доступні після revoke.
Опт-аут webpush відключає pending/verified endpoints; повторне ввімкнення потребує
нового підключення й proof. П’ять активних/нових за годину endpoint на user/facility.
Worker перевіряє eligibility при enqueue, claim і begin, має60s lease, максимум3
спроби з явними retryable відмовами. Невідомий HTTP результат/втрачений finish/
expired dispatch lease → uncertain без blind retry. Old410 обмежено endpoint
version+generation конкретного dispatch. Зміст push загальний, без назв/описів/фото.
HTTP обмежено child process deadline; DNS перевірено, адреса закріплена, TLS SNI
та hostname перевіряються; proxy/cookies/redirect/provider body відсутні.

API: /v1/session/operations/{facility_id}/notifications
GET /preferences → data{user_id,facility_id,version,can_enable,requested,effective,
available,endpoints,vapid_public_key}.
POST /preferences → idempotency_key,expected_version,in_app,webpush,email,telegram.
Receipt: version та точний requested. Restrictive stale save може повернути version
вище expected_version+1; дозвіл нового каналу зі stale version відхиляється.
POST /push/register → idempotency_key,expected_version,endpoint_id,label,opt_in:true,
subscription{endpoint,keys{auth,p256dh},expirationTime?}; requested.webpush мусить
бутиtrue до registration. Receipt — safe endpoint із pending/verified/version.
POST /push/verify → idempotency_key,endpoint_id,nonce; receipt safe endpoint.
POST /push/disable → idempotency_key,endpoint_id,expected_version; receipt disabled,
version=expected+1. POST /read → idempotency_key,notification_id; receipt read_at.
POST errors422 вручну обмежені16KiB JSON, без echo inputs, duplicate/nonfinite
JSON відхилено. Усі mutations через mutation_secret, існуючу SQL session+CSRF.
Receipt resolver domain=preference, target.user_id; інтеграційний010 обов’язковий.
GET board notifications зберігає007 queue_only і додає read_at; приватні team queue
повідомлення відкривають групову чергу, а не чужі деталі заявки.

Client integration
AtlasNotificationClient.connectDevice({facilityId,userId,preferences,label,api,
commandKey?,endpointId?}) викликати безпосередньо у submit/click gesture. Передані
commandKey/endpointId — UUID. Permission prompt запускається до першого await.
Повертає Promise<{endpointId,commandKey,attempt}>. До attempt() немає POST.
attempt.receipt={domain:'preference',key:commandKey}; attempt() повторює точні
subscription/body/key. Caller готує свій синхронний run()+receipt перед bind.
Підготовчий browser failure до POST — definite; некоректний серверний ACK після
POST — uncertain:true. Не зберігати subscription/nonce у local/session storage.
getSubscription() повторно використовує чинну browser subscription. Після зміни
акаунта чужу підписку не переносити; користувач має оновити browser subscription.
attachEvents() транслює тільки перевірені same-origin повідомлення свого worker:
atlas-open-notifications і atlas-notification-settings-changed із facility_id.

Локальна перевірка та реальні межі
tests/test_notifications.py: synthetic crypto/API/worker, справжній pywebpush
encode/http-ece decrypt roundtrip, VAPID signature, DNS/HTTP mocks, actual isolated
child timeout без мережі. tests/test_notification_runtime.py: injected synthetic
credentials/connector, sanitize health. tests/test_notification_client.mjs: VM
browser/SW mocks. Підготовлений notification_pg_check.py викликає combined clone
harness; сам собою цей файл не є SQL PASS. Native systemd/peer/credentials reader,
Linux child lifecycle та реальний browser push в цьому локальному чаті не запускалися.
Чинні кількість тестів/хеші — tests/NOTIFICATIONS_LOCAL_RESULT.json; жодного
зовнішнього повідомлення, реального endpoint або згенерованого native secret.
Native integration порядок — ../integration/NOTIFICATIONS_PROVISIONING_UA.txt.

Перевірені первинні джерела
RFC8030 TTL/urgency/topic/status: https://www.rfc-editor.org/rfc/rfc8030
RFC8291 aes128gcm encrypted payload: https://www.rfc-editor.org/rfc/rfc8291
RFC8292 VAPID audience, ES256/public key: https://www.rfc-editor.org/rfc/rfc8292
W3C Push API (робоча редакція): https://www.w3.org/TR/push-api/
pywebpush2.5.0 release/source: https://pypi.org/project/pywebpush/2.5.0/
https://github.com/web-push-libs/pywebpush/blob/fdc93ec447244647d6393e46ec2cd1a274e4900f/pywebpush/__init__.py
