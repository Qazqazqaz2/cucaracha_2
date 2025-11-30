"""
Trading API endpoints
"""
from flask import request, jsonify
import time
import traceback
from datetime import datetime
from decimal import Decimal

def register_trading_routes(app):
    """Register trading API routes with the Flask app"""
    
    @app.route('/api/v1/trading/swap', methods=['POST'])
    def api_v1_trading_swap():
        """
        API для выполнения обмена токенов
        Требуется: wallet_id, pair, amount, order_type, slippage
        """
        try:
            # Import inside function to avoid circular imports
            from app import (
                get_order_wallet_record, 
                get_pair_pools, 
                pick_pool_by_targets, 
                get_order_wallet_credentials, 
                execute_order_swap,
                DEFAULT_SLIPPAGE
            )
            
            data = request.json or {}
            
            # Параметры обмена
            wallet_id = data.get('wallet_id')
            pair = data.get('pair', 'TON-USDT')
            amount = float(data.get('amount', 0))
            order_type = data.get('order_type', 'long')
            slippage = float(data.get('slippage', DEFAULT_SLIPPAGE))
            
            # Валидация
            if not wallet_id:
                return jsonify({'error': 'wallet_id is required'}), 400
            if amount <= 0:
                return jsonify({'error': 'amount must be positive'}), 400
                
            # Получаем кошелек
            wallet = get_order_wallet_record(int(wallet_id))
            if not wallet:
                return jsonify({'error': 'Wallet not found'}), 404
                
            # Получаем пул для пары
            pair_pools = get_pair_pools(pair)
            if not pair_pools:
                return jsonify({'error': f'No pools found for pair {pair}'}), 404
                
            pool = pick_pool_by_targets(pair, [])
            if not pool:
                return jsonify({'error': f'No suitable pool found for pair {pair}'}), 404
                
            # Создаем временный ордер для обмена
            order_stub = {
                'id': f'api_swap_{int(time.time())}',
                'type': order_type,
                'pair': pair,
                'amount': amount,
                'action': 'open',
                'order_wallet_id': wallet_id,
                'order_wallet': wallet['address']
            }
            
            # Получаем учетные данные кошелька
            creds = get_order_wallet_credentials(order_stub)
            if not creds or not creds.get('mnemonic'):
                return jsonify({'error': 'Wallet mnemonic not found'}), 400
                
            # Выполняем обмен
            swap_result = execute_order_swap(order_stub, pool, creds, slippage=slippage)
            
            return jsonify({
                'success': swap_result.get('success', False),
                'result': swap_result
            })
            
        except Exception as e:
            print(f"[API] Swap error: {e}")
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500