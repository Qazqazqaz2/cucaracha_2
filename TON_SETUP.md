# TON Blockchain Setup for Crypto Exchange Bot

This guide explains how to set up the TON environment for your crypto exchange bot.

## Prerequisites

1. Python 3.7 or higher
2. A Telegram account
3. Access to TON testnet or mainnet

## Installing TON Libraries

We'll use the stable `pytonlib` library for TON integration:

1. **Install the required libraries**:
   ```bash
   pip install -r requirements.txt
   ```

   Or run our installation script:
   ```bash
   python install_ton_libs.py
   ```

## Getting Your Keys

### 1. Telegram Bot Token
- Message [@BotFather](https://t.me/BotFather) on Telegram
- Use the `/newbot` command to create a new bot
- Copy the token provided by BotFather
- Add it to your `.env` file as `TELEGRAM_BOT_TOKEN`

### 2. TON RPC URL
For testnet:
```
TON_RPC_URL=https://testnet.toncenter.com/api/v2/jsonRPC
```

For mainnet:
```
TON_RPC_URL=https://toncenter.com/api/v2/jsonRPC
```

### 3. TON Master Wallet
You have two options:

**Option A: Generate a new wallet**
- Visit [ton.org/dev](https://ton.org/dev)
- Use the web wallet generator to create a new wallet
- Save the 24-word mnemonic phrase securely
- Get the wallet address from the generator

**Option B: Use an existing wallet**
- If you already have a TON wallet, you can use its mnemonic and address

### 4. Jetton Master Address
For testing, you can use these example addresses:

**Testnet Jettons:**
- Test Jetton: `EQAiboDEv_qRrcEdrYdwbVLNOXBHwShFbtKGbQVJ2OKxY0to`
- Test USDT: `EQDQ0-rw6-9xx6t3HcqpfCqO37-2VzxkR13y7LQ6CMqPhSE-`

**To deploy your own Jetton:**
1. Follow the official TON documentation: [Mint your first Jetton](https://docs.ton.org/v3/guidelines/dapps/tutorials/mint-your-first-token)
2. Use the TON Blueprint tool:
   ```bash
   npm install -g @ton/blueprint
   blueprint new my-jetton
   ```

### 5. Admin User ID
- Message [@userinfobot](https://t.me/userinfobot) on Telegram
- Copy your user ID
- Add it to your `.env` file as `ADMIN_USER_ID`

## Environment Variables

Your `.env` file should look like this:

```
BOT_TOKEN=
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TON_RPC_URL=https://testnet.toncenter.com/api/v2/jsonRPC
TON_MASTER_WALLET_MNEMONIC=your_24_word_mnemonic_phrase
TON_MASTER_WALLET_ADDRESS=your_wallet_address
JETTON_MASTER_ADDRESS=jetton_contract_address
ADMIN_USER_ID=your_telegram_user_id
```

## Testing the Setup

1. Make sure all environment variables are set in your `.env` file
2. Test the TON connection:
   ```bash
   python simple_ton_test.py
   ```
3. Run the bot:
   ```bash
   python bot.py
   ```
4. Test the bot by sending `/start` to your bot on Telegram

## Troubleshooting

### Common Issues

1. **Import errors**: Make sure all dependencies are installed:
   ```bash
   pip install -r requirements.txt
   ```

2. **Connection errors**: Check your TON_RPC_URL and internet connection

3. **Authentication errors**: Verify your wallet mnemonic and address are correct

### Getting Help

If you encounter issues:
1. Check the TON documentation: [TON Docs](https://docs.ton.org/)
2. Visit the TON community: [TON Community](https://ton.org/community)
3. Check the GitHub repositories for the libraries used

## How It Works

The bot uses the TON RPC API to interact with the TON blockchain. It can:

1. Check wallet balances
2. Monitor transactions
3. Handle Jetton transfers
4. Display order books for different currency pairs

The bot is designed to work with any Jetton token deployed on the TON blockchain. You can easily add new trading pairs by updating the configuration.