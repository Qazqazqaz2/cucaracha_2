# Bot-Indexator Adaptation

This document explains how the bot.py file was adapted to work with the updated indexator.py.

## Changes Made

### 1. Updated Price Calculation Logic

The price calculation function in bot.py was enhanced to handle edge cases:

```python
# Before
if pool["token0_address"] == jetton_addr and pool["token1_address"] == TON_MASTER:
    price = r1 / r0 if r0 else None
else:
    price = r0 / r1 if r1 else None

# After
if pool["token0_address"] == jetton_addr and pool["token1_address"] == TON_MASTER:
    # jetton is token0, TON is token1
    if r0 and r0 > 0:
        price = r1 / r0
    else:
        price = None
else:
    # jetton is token1, TON is token0
    if r1 and r1 > 0:
        price = r0 / r1
    else:
        price = None
```

### 2. Added Token Validation

Added validation to check if a token exists in the POPULAR_JETTONS dictionary:

```python
jetton_addr = POPULAR_JETTONS.get(symbol)
if not jetton_addr:
    return f"{symbol}/TON: токен не найден"
```

### 3. Improved Error Handling

Enhanced error messages to provide more specific information:

```python
if price is not None:
    return f"{symbol} / TON: {price:.6f} TON"
else:
    return f"{symbol}/TON: ошибка расчёта или нулевые резервы"
```

## Database Schema Compatibility

The bot is now compatible with the updated database schema:

### Jettons Table
- `id` (SERIAL PRIMARY KEY)
- `address` (TEXT UNIQUE NOT NULL)
- `last_checked` (TIMESTAMP WITH TIME ZONE)

### Pools Table
- `id` (SERIAL PRIMARY KEY)
- `pool_address` (TEXT UNIQUE NOT NULL)
- `token0_address` (TEXT NOT NULL)
- `token1_address` (TEXT NOT NULL)
- `lp_fee` (INT)
- `protocol_fee` (INT)
- `last_checked` (TIMESTAMP WITH TIME ZONE)

### Pool Reserves Table
- `id` (SERIAL PRIMARY KEY)
- `pool_id` (INT REFERENCES pools(id) ON DELETE CASCADE)
- `reserve0` (NUMERIC)
- `reserve1` (NUMERIC)
- `checked_at` (TIMESTAMP WITH TIME ZONE)

## Testing

A test script [test_bot_indexator.py](file:///c%3A/Users/armian/Desktop/Works/cryptoExchange/test_bot_indexator.py) was created to verify:

1. Database schema compatibility
2. Data insertion and querying
3. Price calculation functionality

## Benefits of These Changes

1. **Improved Robustness**: Better handling of edge cases like zero reserves
2. **Better Error Messages**: More specific error information for debugging
3. **Enhanced Validation**: Proper validation of token addresses
4. **Schema Compatibility**: Full compatibility with the minimal database schema
5. **Error Prevention**: Prevents division by zero errors

## Usage

The bot can be run as before:

```bash
python bot.py
```

And will now work correctly with the updated indexator that stores only minimal token information in the database.