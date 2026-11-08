# Ежедневные копии базы Cat's House

Отдельный проект Vercel `cats-house-backup` (корень `apps/backup`). Каждую ночь
(расписание `0 2 * * *` по UTC: зимой 03:00–03:59, летом 04:00–04:59 по
времени Белграда) он:

1. снимает стандартную копию базы Neon (`pg_dump` 17.11, формат `custom`);
2. проверяет, что копия читается и в ней есть данные таблиц `people`, `unions`,
   `parent_children`, `events`, `media`;
3. загружает файл `cats-house-ГГГГ-ММ-ДДTЧЧММZ.dump` в Google Drive, в папку
   «Мой диск» → «Cat's House — копии базы», и сверяет контрольную сумму;
4. переводит в корзину Drive лишние старые копии: остаются самая новая, по одной
   за каждый из 30 последних дней и по одной за каждый из 12 последних месяцев;
5. отправляет сигнал сторожу healthchecks.io. Нет сигнала больше суток или
   пришёл сигнал «сбой» — сторож пишет письмо.

Сервис только читает Neon и ничего в нём не меняет. Файлы в Drive он никогда не
удаляет окончательно: корзина Drive хранит их ещё 30 дней. Доступ к Drive у него
только к файлам и папкам, которые он создал сам (`drive.file`). Папку можно
перенести в любое место внутри «Мой диск».

Второй слой защиты — встроенная история изменений Neon (Restore / History
retention в консоли Neon).

## Разовая настройка

Секреты не вводятся в текст команд: они лежат в файлах `~/.config/cats-house/`
с правами `600` и передаются в Vercel через `<` или `|`. Пароли храните также в
1Password.

```bash
mkdir -p ~/.config/cats-house && chmod 700 ~/.config/cats-house
```

### 1. Пользователь Neon только для чтения

Neon → проект `cats-house` → **SQL Editor** (branch `production`):

```sql
CREATE ROLE cats_house_backup LOGIN PASSWORD '<длинный случайный пароль из 1Password>';
GRANT pg_read_all_data TO cats_house_backup;
```

Если Neon не разрешит `pg_read_all_data`, выполните вместо второй строки
(`<база>` — имя базы, обычно `neondb`):

```sql
GRANT CONNECT ON DATABASE <база> TO cats_house_backup;
GRANT USAGE ON SCHEMA public TO cats_house_backup;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO cats_house_backup;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO cats_house_backup;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO cats_house_backup;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO cats_house_backup;
```

Neon → **Connect**: роль `cats_house_backup`, переключатель **Connection
pooling выключен** (прямое подключение). Скопируйте строку подключения (в ней
должно быть `sslmode=require`) и сохраните её в файл из буфера обмена:

```bash
pbpaste > ~/.config/cats-house/backup-db.url && chmod 600 ~/.config/cats-house/backup-db.url
```

### 2. Google Drive

1. [console.cloud.google.com](https://console.cloud.google.com) → создать
   проект `cats-house-backup`.
2. **APIs & Services → Library** → включить **Google Drive API**.
3. **OAuth consent screen** (Google Auth Platform): тип **External**, свой
   адрес почты; в **Data access** добавить только
   `https://www.googleapis.com/auth/drive.file`; в **Audience** нажать
   **Publish app**, чтобы статус стал **In production**. В статусе Testing ключ
   перестаёт действовать через 7 дней. Проверка приложения Google для
   `drive.file` не нужна; при входе Google покажет предупреждение о
   непроверенном приложении — это ваше приложение, нажмите «Продолжить».
4. **Clients → Create client** → тип **Desktop app** → скачать JSON.
5. Выдать доступ (откроется браузер, войдите своим аккаунтом Google):

```bash
python3 apps/backup/scripts/google-authorize.py ~/Downloads/client_secret_*.json
```

Ключи сохранятся в `~/.config/cats-house/backup-google.env`. Скачанный JSON
после этого можно удалить.

### 3. Сторож healthchecks.io

На [healthchecks.io](https://healthchecks.io) создать проверку «Cat's House
backup»: **Period** 1 day, **Grace** 3 hours, уведомления на почту. Скопировать
адрес проверки (`https://hc-ping.com/…`) и сохранить:

```bash
pbpaste > ~/.config/cats-house/backup-healthcheck.url && chmod 600 ~/.config/cats-house/backup-healthcheck.url
```

### 4. Проект Vercel

Создать проект `cats-house-backup` из репозитория с Root Directory
`apps/backup` и привязать папку:

```bash
cd apps/backup && vercel link --project cats-house-backup
```

Секрет запуска (его же Vercel сам передаёт расписанию):

```bash
openssl rand -hex 32 > ~/.config/cats-house/backup-cron.secret && chmod 600 ~/.config/cats-house/backup-cron.secret
```

Переменные Production (значения читаются из файлов):

```bash
vercel env add BACKUP_DATABASE_URL production < ~/.config/cats-house/backup-db.url
```
```bash
vercel env add HEALTHCHECK_URL production < ~/.config/cats-house/backup-healthcheck.url
```
```bash
vercel env add CRON_SECRET production < ~/.config/cats-house/backup-cron.secret
```
```bash
grep '^GOOGLE_CLIENT_ID=' ~/.config/cats-house/backup-google.env | cut -d= -f2- | vercel env add GOOGLE_CLIENT_ID production
```
```bash
grep '^GOOGLE_CLIENT_SECRET=' ~/.config/cats-house/backup-google.env | cut -d= -f2- | vercel env add GOOGLE_CLIENT_SECRET production
```
```bash
grep '^GOOGLE_REFRESH_TOKEN=' ~/.config/cats-house/backup-google.env | cut -d= -f2- | vercel env add GOOGLE_REFRESH_TOKEN production
```

Отметьте переменные как **Sensitive** в Vercel, затем опубликуйте:

```bash
vercel deploy --prod
```

## Запустить копию вручную

```bash
cd apps/backup && vercel curl /api/backup -- --header "Authorization: Bearer $(cat ~/.config/cats-house/backup-cron.secret)"
```

Ответ: `{"file": "cats-house-…Z.dump", "size": …, "kept": …, "trashed": [...]}`.
Без заголовка — `401 {"error": "Нет доступа."}`.

## Восстановление

1. Drive → «Cat's House — копии базы» → скачать нужный файл `.dump`.
2. Создать пустую базу для восстановления: Neon → проект `cats-house` →
   **Databases → New database** (например `restore_ГГГГММДД`), или пустую
   локальную базу PostgreSQL 17. Строку подключения сохранить в файл, как в
   шаге 1 настройки (например `~/.config/cats-house/restore-db.url`).
3. Восстановить. `pg_restore` 17 на Mac появляется в
   `/tmp/cats-house-pg/postgresql-17.11.0-aarch64-apple-darwin/bin/` после
   первого запуска скрипта проверки (раздел ниже); подойдёт и любой
   `pg_restore` версии 17 и новее:

```bash
/tmp/cats-house-pg/postgresql-17.11.0-aarch64-apple-darwin/bin/pg_restore --no-owner --no-privileges --exit-on-error -d "$(cat ~/.config/cats-house/restore-db.url)" ~/Downloads/cats-house-ГГГГ-ММ-ДДTЧЧММZ.dump
```

4. Проверить сайт на восстановленной базе: в Vercel → `cats-house-api` →
   **Settings → Environment Variables** заменить `CATS_HOUSE_DATABASE_URL`
   строкой подключения восстановленной базы (роль владельца базы, не
   `cats_house_backup`; TLS обязателен), сохранить и сделать Production
   **Redeploy**. Старую базу не удалять, пока сайт не проверен.

## Проверка раз в квартал

Скачать свежую копию из Drive и восстановить её во временную базу на Mac (нужен
Docker). Скрипт сравнит число строк во всех таблицах и содержимое всех файлов с
Neon:

```bash
CATS_HOUSE_SOURCE_DATABASE_URL="$(cat ~/.config/cats-house/backup-db.url)" apps/backup/.venv/bin/python apps/backup/scripts/verify-backup-file.py ~/Downloads/cats-house-ГГГГ-ММ-ДДTЧЧММZ.dump
```

Ожидаемо: «Копия восстанавливается и совпадает с базой.» Если базу правили
после копии, расхождения в числе строк нормальны.

## Если пришло письмо от сторожа

| Текст ошибки | Что делать |
| --- | --- |
| нет сигнала (Down), ошибки нет | Vercel → `cats-house-backup` → **Logs** и **Settings → Cron Jobs**; запустить копию вручную |
| «ключ доступа Google не действует» | Повторить шаг 2.5 и заменить три переменные `GOOGLE_*`, затем Redeploy |
| «pg_dump завершился с ошибкой» | Проверить в Neon, что база работает, и пароль роли `cats_house_backup`; при смене пароля обновить `BACKUP_DATABASE_URL` и сделать Redeploy |
| «копия неполная» или «не читается» | Запустить копию вручную; если повторяется — не менять базу и разобраться с причиной |
| «файл в Google Drive не совпал» | Запустить копию вручную; старые копии при этом не тронуты |
| «Не заданы настройки: …» | Добавить названные переменные в Vercel и сделать Redeploy |

## Разработка

```bash
cd apps/backup && /opt/homebrew/bin/python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```
```bash
cd apps/backup && .venv/bin/pytest -q
```

Тесты используют выдуманные данные и временную базу PostgreSQL 17 в Docker.
