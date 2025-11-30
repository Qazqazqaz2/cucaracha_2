# Инструкция по использованию API системы торговли TON

## Обзор
Этот документ описывает использование нового унифицированного API для интеграции с системой торговли TON. API предоставляет функции для торговли, управления кошельками, управления ордерами и получения информации о токенах/парах.

## Базовый URL
```
http://localhost:5000/api/v1
```

## Аутентификация
Для тестирования аутентификация не требуется. В продакшене следует реализовать соответствующую аутентификацию.

## Эндпоинты API

### Торговля

#### Выполнение обмена токенов
Выполняет операцию обмена токенов.

**Эндпоинт:** `POST /trading/swap`

**Тело запроса:**
```json
{
  "wallet_id": 1,
  "pair": "TON-USDT",
  "amount": 1.0,
  "order_type": "long",
  "slippage": 1.0
}
```

**Ответ:**
```json
{
  "success": true,
  "result": {
    // Результат выполнения обмена
  }
}
```

### Кошельки

#### Получение списка кошельков
Получает список кошельков пользователя.

**Эндпоинт:** `GET /wallets?owner_wallet=<address>`

**Ответ:**
```json
{
  "success": true,
  "wallets": [
    {
      "id": 1,
      "owner_wallet": "owner_address",
      "address": "wallet_address",
      "label": "My Wallet",
      "created_at": "2023-01-01T00:00:00",
      "updated_at": "2023-01-01T00:00:00",
      "has_mnemonic": true
    }
  ]
}
```

#### Создание кошелька
Создает новый кошелек.

**Эндпоинт:** `POST /wallets`

**Тело запроса:**
```json
{
  "owner_wallet": "owner_address",
  "address": "wallet_address",
  "label": "My New Wallet",
  "mnemonic": "word1 word2 ... word24"
}
```

**Ответ:**
```json
{
  "success": true,
  "wallet": {
    "id": 2,
    "owner_wallet": "owner_address",
    "address": "wallet_address",
    "label": "My New Wallet",
    "created_at": "2023-01-01T00:00:00",
    "updated_at": "2023-01-01T00:00:00",
    "has_mnemonic": true
  }
}
```

#### Получение информации о кошельке
Получает информацию о конкретном кошельке.

**Эндпоинт:** `GET /wallets/{wallet_id}`

**Ответ:**
```json
{
  "success": true,
  "wallet": {
    "id": 1,
    "owner_wallet": "owner_address",
    "address": "wallet_address",
    "label": "My Wallet",
    "created_at": "2023-01-01T00:00:00",
    "updated_at": "2023-01-01T00:00:00",
    "has_mnemonic": true
  }
}
```

#### Получение балансов кошелька
Получает балансы токенов кошелька.

**Эндпоинт:** `GET /wallets/{wallet_id}/balances`

**Ответ:**
```json
{
  "success": true,
  "address": "wallet_address",
  "tokens": [
    {
      "symbol": "TON",
      "balance": 10.5
    }
  ],
  "balance": 10.5
}
```

#### Перевод средств
Переводит средства с кошелька.

**Эндпоинт:** `POST /wallets/{wallet_id}/transfer`

**Тело запроса:**
```json
{
  "destination": "recipient_address",
  "amount": 1.0,
  "comment": "Payment",
  "token": "TON"
}
```

**Ответ:**
```json
{
  "success": true,
  "result": {
    // Результат перевода
  }
}
```

### Ордера

#### Создание ордера
Создает новый ордер.

**Эндпоинт:** `POST /orders`

**Тело запроса:**
```json
{
  "symbol": "TON-USDT",
  "quantity": 1.0,
  "order_type": "LIMIT",
  "side": "LONG",
  "limit_price": 7.5,
  "stop_price": 7.0,
  "take_profit": 8.0,
  "stop_loss": 7.0,
  "max_slippage": 0.5,
  "user_wallet": "user_address",
  "entry_price": 7.5,
  "order_wallet_id": 1
}
```

**Ответ:**
```json
{
  "success": true,
  "order": {
    // Детали ордера
  },
  "gas_info": {
    "gas_amount": 0.1,
    "total_amount": 1.1,
    "from_token": "TON",
    "to_token": "USDT"
  }
}
```

#### Получение списка ордеров
Получает список ордеров.

**Эндпоинт:** `GET /orders?user_wallet=<address>`

**Ответ:**
```json
{
  "success": true,
  "orders": [
    {
      // Детали ордера
    }
  ]
}
```

#### Получение информации об ордере
Получает информацию о конкретном ордере.

**Эндпоинт:** `GET /orders/{order_id}`

**Ответ:**
```json
{
  "success": true,
  "order": {
    // Детали ордера
  }
}
```

#### Отмена ордера
Отменяет ордер.

**Эндпоинт:** `DELETE /orders/{order_id}`

**Ответ:**
```json
{
  "success": true,
  "message": "Order cancelled"
}
```

### Пары

#### Получение всех пар
Получает информацию обо всех торговых парах.

**Эндпоинт:** `GET /pairs`

**Ответ:**
```json
{
  "success": true,
  "pairs": {
    "TON-USDT": {
      "name": "TON-USDT",
      "pools": [
        {
          "address": "pool_address",
          "dex": "DeDust",
          "from_token": "TON",
          "to_token": "USDT",
          "price": 7.5
        }
      ],
      "current_price": 7.5
    }
  }
}
```

#### Получение информации о паре
Получает информацию о конкретной торговой паре.

**Эндпоинт:** `GET /pairs/{pair_name}`

**Ответ:**
```json
{
  "success": true,
  "pair": {
    "name": "TON-USDT",
    "pools": [
      {
        "address": "pool_address",
        "dex": "DeDust",
        "from_token": "TON",
        "to_token": "USDT",
        "price": 7.5
      }
    ],
    "current_price": 7.5
  }
}
```

### Токены

#### Получение всех токенов
Получает список всех доступных токенов.

**Эндпоинт:** `GET /tokens`

**Ответ:**
```json
{
  "success": true,
  "tokens": ["TON", "USDT"]
}
```

### Котировки

#### Получение котировки
Получает котировку обмена для токеновой пары.

**Эндпоинт:** `GET /quote?pair=TON-USDT&amount=1.0&slippage=1.0`

**Ответ:**
```json
{
  "success": true,
  "pair": "TON-USDT",
  "amount": 1.0,
  "slippage": 1.0,
  "best_quote": {
    "dex": "DeDust",
    "pool_address": "pool_address",
    "output": 7.5,
    "min_output": 7.425,
    "price": 7.5,
    "from_token": "TON",
    "to_token": "USDT"
  },
  "all_quotes": [
    // Все котировки из разных пулов
  ]
}
```

## Ответы об ошибках
Все ответы об ошибках следуют этому формату:
```json
{
  "error": "Описание ошибки"
}
```

## Коды состояния
- `200` - Успех
- `400` - Неверный запрос
- `404` - Не найдено
- `500` - Внутренняя ошибка сервера

## Примеры интеграции

### Пример на Python
```python
import requests

# Создание ордера
order_data = {
    "symbol": "TON-USDT",
    "quantity": 1.0,
    "order_type": "LIMIT",
    "side": "LONG",
    "limit_price": 7.5,
    "order_wallet_id": 1
}

response = requests.post("http://localhost:5000/api/v1/orders", json=order_data)
if response.status_code == 200:
    result = response.json()
    print(f"Ордер создан: {result['order']['id']}")
else:
    print(f"Ошибка: {response.json()['error']}")
```

### Пример на JavaScript
```javascript
// Получение котировки токена
fetch('http://localhost:5000/api/v1/quote?pair=TON-USDT&amount=1.0')
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      console.log(`Лучшая цена: ${data.best_quote.price} USDT за TON`);
    } else {
      console.error(`Ошибка: ${data.error}`);
    }
  })
  .catch(error => console.error('Ошибка сети:', error));
```

## Особенности использования

### Расчет газа
Все торговые операции включают расчет необходимого газа:
- Автоматический расчет газа для каждой операции
- Отображение общей требуемой суммы (сумма + газ)
- Поддержка различных DEX (DeDust, StonFi)

### Управление ордерами
- Поддержка всех типов ордеров (LIMIT, MARKET, STOP_LOSS, TAKE_PROFIT, STOP_ENTRY)
- Возможность создания OCO ордеров (One Cancels Other)
- Поддержка трейлинг-стопов
- Расчет проскальзывания

### Управление кошельками
- Создание и управление торговыми кошельками
- Хранение мнемоник с шифрованием
- Получение балансов токенов
- Перевод средств между кошельками

## Рекомендации по использованию

1. **Проверка баланса**: Всегда проверяйте баланс кошелька перед выполнением операций
2. **Установка проскальзывания**: Используйте разумные значения проскальзывания для защиты от больших изменений цен
3. **Обработка ошибок**: Всегда обрабатывайте ошибки API в вашем коде
4. **Тестирование**: Тщательно тестируйте все операции в тестовой среде перед использованием в продакшене

## Поддержка
Если у вас возникли проблемы с использованием API, обратитесь к технической документации или свяжитесь с поддержкой.