# Database Extraction Changes

This document explains the changes made to ensure that only token contract addresses are extracted and stored in the database.

## Problem Statement

The original code was attempting to store full token objects in the database, which was not the desired behavior. We needed to modify the code to extract only the contract addresses for [token0_address](file:///c%3A/Users/armian/Desktop/Works/cryptoExchange/indexator.py#L157-L157) and [token1_address](file:///c%3A/Users/armian/Desktop/Works/cryptoExchange/indexator.py#L161-L161) and store only these addresses in the database.

Additionally, the database schema was storing unnecessary token information like symbols, names, decimals, and total supply, which violated the data minimization policy.

## Changes Made

### 1. Modified Database Schema

The database schema was updated to store only minimal information:

**Before:**
```sql
CREATE TABLE IF NOT EXISTS jettons (
  id SERIAL PRIMARY KEY,
  address TEXT UNIQUE NOT NULL,
  symbol TEXT,
  name TEXT,
  decimals INT,
  total_supply NUMERIC,
  last_checked TIMESTAMP WITH TIME ZONE DEFAULT now()
);
```

**After:**
```sql
CREATE TABLE IF NOT EXISTS jettons (
  id SERIAL PRIMARY KEY,
  address TEXT UNIQUE NOT NULL,
  last_checked TIMESTAMP WITH TIME ZONE DEFAULT now()
);
```

### 2. Modified [upsert_pool_and_tokens](file://c:\Users\armian\Desktop\Works\cryptoExchange\indexator.py#L168-L216) Function

The main change was in the [upsert_pool_and_tokens](file://c:\Users\armian\Desktop\Works\cryptoExchange\indexator.py#L168-L216) function in [indexator.py](file:///c%3A/Users/armian/Desktop/Works/cryptoExchange/indexator.py):

**Before:**
```python
# The function was trying to store full token objects
token0_address = item.get("token0_address", {})
token1_address = item.get("token1_address", {})
```

**After:**
```python
# Получаем только адреса контрактов токенов
token0_data = pool_obj.get("token0_address")
token1_data = pool_obj.get("token1_address")

# Извлекаем адреса контрактов из различных форматов данных
token0_address = None
token1_address = None

# Для token0
if isinstance(token0_data, str):
    # Прямая строка с адресом
    if token0_data.startswith(('EQ', 'UQ', '0:')) or ':' in token0_data:
        token0_address = token0_data
elif isinstance(token0_data, dict):
    # Словарь с данными токена
    for key in ['address', 'tokenAddress', 'token_address']:
        addr = token0_data.get(key)
        if isinstance(addr, str) and (addr.startswith(('EQ', 'UQ', '0:')) or ':' in addr):
            token0_address = addr
            break

# Для token1 (similar logic)
```

### 3. Enhanced [extract_addr](file://c:\Users\armian\Desktop\Works\cryptoExchange\indexator.py#L139-L165) Function

We also enhanced the [extract_addr](file://c:\Users\armian\Desktop\Works\cryptoExchange\indexator.py#L139-L165) function to better handle different data formats:

```python
def extract_addr(token_field: Any) -> str:
    """
    Извлекает адрес контракта из различных форматов данных.
    Гарантированно возвращает только адрес или None.
    """
    if token_field is None:
        return None
    
    # Если это строка, проверяем что это валидный адрес TON
    if isinstance(token_field, str):
        # Простая проверка на формат адреса TON
        if token_field.startswith(('EQ', 'UQ', '0:')) or ':' in token_field:
            return token_field
        return None
    
    # Если это словарь, ищем поле с адресом
    if isinstance(token_field, dict):
        # Пробуем различные ключи, которые могут содержать адрес
        address_keys = ['address', 'tokenAddress', 'master', 'walletAddress', 
                       'token_address', 'token_wallet_address', 'contract_address']
        for key in address_keys:
            if key in token_field and isinstance(token_field[key], str):
                addr = token_field[key]
                # Простая проверка на формат адреса TON
                if addr.startswith(('EQ', 'UQ', '0:')) or ':' in addr:
                    return addr
    
    return None
```

## What Gets Stored in the Database

After these changes, only the following information is stored in the database:

1. **Pool Information:**
   - `pool_address` - The contract address of the liquidity pool
   - `token0_address` - Only the contract address of token0 (no other token data)
   - `token1_address` - Only the contract address of token1 (no other token data)
   - `lp_fee` - Liquidity provider fee
   - `protocol_fee` - Protocol fee
   - `last_checked` - Timestamp of last update

2. **Jetton Information:**
   - `address` - Only the contract address of each jetton (no other token data)
   - `last_checked` - Timestamp of last update

3. **Pool Reserves:**
   - `pool_id` - Reference to the pool
   - `reserve0` - Reserve amount for token0
   - `reserve1` - Reserve amount for token1
   - `checked_at` - Timestamp of when reserves were checked

## Removed Fields

The following fields have been removed from the database schema:

1. **From jettons table:**
   - `symbol` - Token symbol
   - [name](file://c:\Users\armian\Desktop\Works\cryptoExchange\toncli\src\toncli\modules\utils\system\project_conf.py#L20-L20) - Token name
   - `decimals` - Token decimals
   - `total_supply` - Token total supply

## Database Migration

To update an existing database to the new minimal schema, you can use the provided migration scripts:

1. **[recreate_tables.py](file:///c%3A/Users/armian/Desktop/Works/cryptoExchange/recreate_tables.py)** - Drops and recreates tables with the new schema
2. **[db_migration.py](file:///c%3A/Users/armian/Desktop/Works/cryptoExchange/db_migration.py)** - Migrates existing data to the new schema

## Testing

We created comprehensive tests to verify that the changes work correctly:

1. **[test_db_extraction.py](file:///c%3A/Users/armian/Desktop/Works/cryptoExchange/test_db_extraction.py)** - Tests the database extraction functionality
2. **[test_extract_addr.py](file:///c%3A/Users/armian/Desktop/Works/cryptoExchange/test_extract_addr.py)** - Tests the address extraction function
3. **[test_real_pool.py](file:///c%3A/Users/armian/Desktop/Works/cryptoExchange/test_real_pool.py)** - Tests with simulated real pool data
4. **[test_minimal_db.py](file:///c%3A/Users/armian/Desktop/Works/cryptoExchange/test_minimal_db.py)** - Tests that the database has the correct minimal schema

All tests pass, confirming that only contract addresses are extracted and stored in the database with the minimal schema.

## Benefits of These Changes

1. **Data Consistency:** Only the necessary contract addresses are stored, ensuring consistency in the database schema.
2. **Reduced Storage:** Storing only addresses instead of full objects reduces database storage requirements.
3. **Improved Performance:** Smaller data size leads to faster database operations.
4. **Clearer Data Model:** The database now contains only the specific information needed for the application.
5. **Compliance:** The changes comply with data minimization policies by storing only essential information.
6. **Privacy:** Less sensitive data is stored, reducing privacy risks.