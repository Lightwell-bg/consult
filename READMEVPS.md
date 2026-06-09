# Деплой на VPS с Docker

Инструкция для развёртывания бота на Linux VPS (Ubuntu 22.04 / Debian 12).

---

## Требования к серверу

- Ubuntu 22.04 LTS или Debian 12
- Минимум 512 МБ RAM (рекомендуется 1 ГБ)
- Доступ к серверу по SSH

---

## 1. Установка Docker

```bash
# Обновить пакеты
sudo apt update && sudo apt upgrade -y

# Установить зависимости
sudo apt install -y ca-certificates curl gnupg

# Добавить GPG-ключ Docker
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Добавить репозиторий
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Установить Docker Engine и Compose
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Запустить и добавить в автозагрузку
sudo systemctl enable --now docker

# Разрешить текущему пользователю работать с Docker без sudo (требует перелогина)
sudo usermod -aG docker $USER
newgrp docker
```

Проверить установку:
```bash
docker --version
docker compose version
```

---

## 2. Загрузить проект на сервер

### Вариант A — git clone

```bash
git clone <repo-url> /opt/consult
cd /opt/consult
```

### Вариант B — scp с локальной машины

```bash
scp -r ./consult user@your-server-ip:/opt/consult
ssh user@your-server-ip
cd /opt/consult
```

---

## 3. Настроить переменные окружения

```bash
cp .env.example .env
nano .env
```

Заполните все значения в `.env`:

```env
TELEGRAM_BOT_TOKEN=ваш_токен
ANTHROPIC_API_KEY=ваш_api_ключ
ANTHROPIC_MODEL=claude-sonnet-4-20250514
GOOGLE_SERVICE_ACCOUNT_FILE=credentials/google-service-account.json
DATABASE_PATH=data/bot.db
LOG_LEVEL=INFO
```

---

## 4. Загрузить Google Service Account JSON

Скопируйте JSON-ключ с локальной машины на сервер:

```bash
# На локальной машине
scp credentials/google-service-account.json user@your-server-ip:/opt/consult/credentials/

# Или создайте файл вручную на сервере
mkdir -p /opt/consult/credentials
nano /opt/consult/credentials/google-service-account.json
# Вставьте содержимое JSON-ключа
```

Проверьте права доступа:
```bash
chmod 600 /opt/consult/credentials/google-service-account.json
```

---

## 5. Создать директорию для данных

```bash
mkdir -p /opt/consult/data
```

---

## 6. Добавить первого администратора

Перед запуском бота нужно добавить хотя бы одного администратора в базу данных.

```bash
cd /opt/consult

# Инициализировать БД и добавить администратора
docker compose run --rm bot python scripts/seed_admin.py 123456789 --admin
```

Если бот ещё не собирался — сначала соберите образ:
```bash
docker compose build
docker compose run --rm bot python scripts/seed_admin.py 123456789 --admin
```

---

## 7. Запустить бота

```bash
cd /opt/consult
docker compose up -d
```

Проверить статус:
```bash
docker compose ps
```

---

## Управление

### Просмотр логов

```bash
# Последние 100 строк
docker compose logs --tail=100 bot

# В режиме реального времени
docker compose logs -f bot
```

### Остановить бота

```bash
docker compose stop
```

### Перезапустить бота

```bash
docker compose restart bot
```

### Обновить код и перезапустить

```bash
cd /opt/consult
git pull
docker compose build
docker compose up -d
```

### Просмотр состояния контейнера

```bash
docker compose ps
docker stats consult-bot-1
```

---

## Резервное копирование SQLite

База данных хранится в `./data/bot.db`. Для резервного копирования достаточно скопировать этот файл.

### Ручное копирование

```bash
cp /opt/consult/data/bot.db /opt/consult/data/bot.db.backup.$(date +%Y%m%d)
```

### Автоматический бэкап через cron

```bash
crontab -e
```

Добавьте строку (бэкап каждый день в 3:00):

```cron
0 3 * * * cp /opt/consult/data/bot.db /opt/backups/bot.db.$(date +\%Y\%m\%d) 2>/dev/null
```

Создайте директорию для бэкапов:
```bash
sudo mkdir -p /opt/backups
sudo chown $USER:$USER /opt/backups
```

---

## Обновление системных промптов

Файлы `prompts/*.md` монтируются не в Docker-образ, а копируются при сборке. После изменения промптов нужно пересобрать образ:

```bash
cd /opt/consult
# Отредактируйте prompts/system.md или prompts/fallback.md
docker compose build
docker compose up -d
```

Либо, если хотите обновлять промпты без пересборки, добавьте в `docker-compose.yml` volume для prompts:

```yaml
volumes:
  - ./data:/app/data
  - ./credentials:/app/credentials:ro
  - ./prompts:/app/prompts:ro   # добавить эту строку
```

---

## Брандмауэр

Бот не слушает входящие порты — он работает через long polling. Дополнительная настройка брандмауэра для бота не нужна. Убедитесь только, что сервер имеет доступ к интернету для связи с Telegram API и Anthropic API.

---

## Troubleshooting

### Бот не запускается — проверить логи

```bash
docker compose logs bot
```

Типичные причины:
- Неверный `TELEGRAM_BOT_TOKEN`
- Нет файла `credentials/google-service-account.json`
- Таблица не расшарена на email сервисного аккаунта

### Бот не отвечает на сообщения

1. Убедитесь, что ваш Telegram ID в белом списке (`/whoami` → `seed_admin.py`).
2. Проверьте, что база знаний загружена (`/status` в боте).

### Ошибка доступа к Google Sheets

Убедитесь, что:
1. API Google Sheets включён в вашем Google Cloud проекте.
2. Таблица расшарена на email сервисного аккаунта (не просто публично).
3. Email аккаунта из JSON совпадает с тем, которому открыт доступ.
