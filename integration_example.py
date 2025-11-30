#!/usr/bin/env python3
"""
Пример интеграции с новым API для создания торговой системы
"""

import requests
import json
import time

class TradingAPI:
    def __init__(self, base_url="http://localhost:5000/api/v1"):
        self.base_url = base_url
        
    def get_pairs(self):
        """Получить список торговых пар"""
        response = requests.get(f"{self.base_url}/pairs")
        return response.json() if response.status_code == 200 else None
        
    def get_quote(self, pair="TON-USDT", amount=1.0, slippage=1.0):
        """Получить котировку для пары"""
        params = {
            "pair": pair,
            "amount": amount,
            "slippage": slippage
        }
        response = requests.get(f"{self.base_url}/quote", params=params)
        return response.json() if response.status_code == 200 else None
        
    def get_wallets(self, owner_wallet=None):
        """Получить список кошельков"""
        params = {"owner_wallet": owner_wallet} if owner_wallet else {}
        response = requests.get(f"{self.base_url}/wallets", params=params)
        return response.json() if response.status_code == 200 else None
        
    def create_wallet(self, owner_wallet, address, label=None, mnemonic=None):
        """Создать новый кошелек"""
        data = {
            "owner_wallet": owner_wallet,
            "address": address
        }
        if label:
            data["label"] = label
        if mnemonic:
            data["mnemonic"] = mnemonic
            
        response = requests.post(f"{self.base_url}/wallets", json=data)
        return response.json() if response.status_code == 200 else None
        
    def get_wallet_balances(self, wallet_id):
        """Получить балансы кошелька"""
        response = requests.get(f"{self.base_url}/wallets/{wallet_id}/balances")
        return response.json() if response.status_code == 200 else None
        
    def create_order(self, symbol, quantity, order_type, side, 
                    limit_price=None, stop_price=None, take_profit=None, 
                    stop_loss=None, order_wallet_id=None):
        """Создать ордер"""
        data = {
            "symbol": symbol,
            "quantity": quantity,
            "order_type": order_type,
            "side": side
        }
        
        if limit_price:
            data["limit_price"] = limit_price
        if stop_price:
            data["stop_price"] = stop_price
        if take_profit:
            data["take_profit"] = take_profit
        if stop_loss:
            data["stop_loss"] = stop_loss
        if order_wallet_id:
            data["order_wallet_id"] = order_wallet_id
            
        response = requests.post(f"{self.base_url}/orders", json=data)
        return response.json() if response.status_code == 200 else None
        
    def get_orders(self, user_wallet=None):
        """Получить список ордеров"""
        params = {"user_wallet": user_wallet} if user_wallet else {}
        response = requests.get(f"{self.base_url}/orders", params=params)
        return response.json() if response.status_code == 200 else None
        
    def cancel_order(self, order_id):
        """Отменить ордер"""
        response = requests.delete(f"{self.base_url}/orders/{order_id}")
        return response.json() if response.status_code == 200 else None

def main():
    """Основной пример использования"""
    print("=== Пример интеграции с Trading API ===")
    
    # Создаем клиент API
    api = TradingAPI()
    
    # 1. Получаем список торговых пар
    print("\n1. Получение торговых пар...")
    pairs = api.get_pairs()
    if pairs and pairs.get("success"):
        print(f"Найдено пар: {len(pairs['pairs'])}")
        for pair_name, pair_info in pairs["pairs"].items():
            print(f"  {pair_name}: {pair_info['current_price']:.4f}")
    else:
        print("Ошибка получения пар")
        
    # 2. Получаем котировку
    print("\n2. Получение котировки...")
    quote = api.get_quote("TON-USDT", 1.0)
    if quote and quote.get("success"):
        best = quote["best_quote"]
        print(f"Лучшая котировка: {best['output']:.6f} {best['to_token']} за {quote['amount']} {best['from_token']}")
        print(f"Цена: {best['price']:.4f} {best['to_token']}/{best['from_token']} через {best['dex']}")
    else:
        print("Ошибка получения котировки")
        
    # 3. Получаем список кошельков
    print("\n3. Получение кошельков...")
    wallets = api.get_wallets()
    if wallets and wallets.get("success"):
        print(f"Найдено кошельков: {len(wallets['wallets'])}")
        for wallet in wallets["wallets"]:
            print(f"  #{wallet['id']}: {wallet['address'][:10]}... ({wallet['label']})")
    else:
        print("Ошибка получения кошельков")
        
    # 4. Создаем ордер (пример)
    print("\n4. Создание ордера (пример)...")
    # Примечание: для реального создания ордера нужен существующий wallet_id
    # order = api.create_order(
    #     symbol="TON-USDT",
    #     quantity=1.0,
    #     order_type="LIMIT",
    #     side="LONG",
    #     limit_price=7.5,
    #     order_wallet_id=1  # Замените на реальный ID кошелька
    # )
    # if order and order.get("success"):
    #     print(f"Ордер создан: {order['order']['id']}")
    #     if "gas_info" in order:
    #         gas = order["gas_info"]
    #         print(f"  Газ: {gas['gas_amount']:.6f} TON")
    #         print(f"  Всего: {gas['total_amount']:.6f} TON")
    # else:
    #     print("Ошибка создания ордера")
        
    print("\n=== Интеграция завершена ===")

if __name__ == "__main__":
    main()