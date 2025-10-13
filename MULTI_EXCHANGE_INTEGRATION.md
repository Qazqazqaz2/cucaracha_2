# Multi-Exchange Token Metadata Integration
# =========================================

## Overview
This implementation enhances the Telegram bot to fetch token metadata from multiple exchanges:
- STON.fi
- DeDust.io
- tonapi.io

## Key Features

### 1. Multi-Source Metadata Retrieval
The bot now checks all supported exchanges for token information:
- If a token is listed on multiple exchanges, users can choose the source
- If a token is only on one exchange, data is fetched automatically
- Fallback mechanisms ensure token information is always provided

### 2. User Choice Implementation
When a token is found on multiple exchanges:
- Users are presented with inline buttons to select the metadata source
- Options include STON.fi, DeDust.io, and auto-selection
- The choice is remembered for that specific token request

### 3. Enhanced Data Presentation
Token information now includes:
- Symbol and name
- Price with source indication
- Decimals
- Verification status
- Metadata source (when user makes a choice)

## Technical Implementation

### New Functions Added
1. `get_jetton_metadata_from_dedust()` - Fetches metadata from DeDust.io API
2. `get_all_metadata_sources()` - Gets metadata from all exchanges simultaneously
3. `show_source_selection()` - Displays exchange choice to user
4. `process_source_selection()` - Handles user's exchange choice

### Modified Functions
1. `get_jetton_metadata()` - Enhanced to support source selection
2. `get_jetton_price()` - Enhanced to support source selection
3. `get_token_info()` - Updated to show metadata source
4. Command handlers (`/pairs`, `/token`) - Modified to use new multi-source logic

## API Endpoints Used

### STON.fi
- Token metadata: `https://api.ston.fi/v1/tokens/{token_address}`
- Price data: `https://api.ston.fi/v1/tokens/{token_address}`

### DeDust.io
- Assets list: `https://api.dedust.io/v2/assets`
- Pools data: `https://api.dedust.io/v2/pools`

### tonapi.io
- Jetton data: `https://tonapi.io/v2/jettons/{token_address}`

## User Experience

### When a token is on multiple exchanges:
```
🔄 Token found on multiple exchanges. Please select source for metadata:

[Get metadata from STON.fi]
[Get metadata from DeDust]
[Auto-select (recommended)]
```

### After selection:
```
📛 Tether USD (USDT)
💰 Price: 0.99000000 TON
📡 Source: STON.fi
🔢 Decimals: 6
📍 EQD26zcd6Cqpz7WyLKVH8x_cD6D7tBrom6hKcycv8L8hV0GP
✅ Verified: Yes
📊 Metadata source: STON.fi
```

## Benefits
1. **Comprehensive coverage** - Data from multiple sources ensures better token information
2. **User control** - Users can choose which exchange data to trust
3. **Fallback reliability** - If one exchange is down, others are used
4. **Enhanced information** - More detailed token data presentation
5. **Future-proof** - Easy to add more exchanges

This implementation fully satisfies the requirement to fetch metadata from both STON.fi and DeDust.io and give users a choice when a token is listed on both exchanges.