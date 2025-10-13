# Crypto Exchange Bot

Telegram бот для работы с криптовалютными биржами и TON блокчейном.

## Возможности

- Интеграция с TON блокчейном
- Работа с различными криптовалютными биржами
- Система индексации токенов
- Автоматическое обновление цен
- База данных для хранения информации о токенах
- Система бэкапов

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/Qazqazqaz2/cucaracha_2.git
cd cucaracha_2
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Настройте конфигурацию в файле `config.json`

## Использование

### Запуск бота
```bash
python bot.py
```

### Система бэкапов

Проект включает автоматическую систему бэкапов в GitHub.

#### Создание бэкапа
```bash
python backup_script.py backup
# или
backup.bat backup
```

#### Восстановление из бэкапа
```bash
python backup_script.py restore
# или
backup.bat restore
```

#### Просмотр истории бэкапов
```bash
python backup_script.py history
# или
backup.bat history
```

#### Проверка статуса
```bash
python backup_script.py status
# или
backup.bat status
```

## Структура проекта

- `bot.py` - основной файл бота
- `indexator.py` - система индексации токенов
- `price_updater.py` - обновление цен
- `db_migration.py` - миграции базы данных
- `backup_script.py` - скрипт для бэкапов
- `requirements.txt` - зависимости Python

## Конфигурация

Создайте файл `config.json` с настройками:
```json
{
    "telegram_token": "YOUR_BOT_TOKEN",
    "database_url": "sqlite:///exchange.db",
    "ton_api_key": "YOUR_TON_API_KEY"
}
```

## База данных

Проект использует SQLite для хранения данных. Файлы базы данных исключены из Git репозитория для безопасности.

## Бэкапы

Все изменения автоматически сохраняются в GitHub репозитории. Используйте скрипт `backup_script.py` для управления бэкапами.

## Лицензия

MIT License
