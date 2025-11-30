"""
Orders API endpoints
"""
from flask import request, jsonify
import time
import traceback
from datetime import datetime
from decimal import Decimal

def register_orders_routes(app):
    """Register orders API routes with the Flask app"""
    
    @app.route('/api/v1/orders', methods=['POST'])
    def api_v1_create_order():
        """
        API для создания ордера
        Требуется: symbol, quantity, order_type, side
        """
        try:
            # Import inside function to avoid circular imports
            from app import (
                get_order_wallet_record,
                get_pair_pools,
                DEFAULT_SLIPPAGE
            )
            from order_engine import get_order_engine
            
            data = request.json or {}
            engine = get_order_engine()
            
            # Get order wallet address from app context
            from app import order_wallet_address, _default_wallet
            
            # Определяем кошелек
            wallet_id = data.get('order_wallet_id')
            wallet_address = None
            if wallet_id:
                wallet = get_order_wallet_record(int(wallet_id))
                if wallet:
                    wallet_address = wallet['address']
            if not wallet_address and order_wallet_address:
                wallet_address = order_wallet_address
                wallet_id = wallet_id or (_default_wallet['id'] if _default_wallet else None)
                
            # Валидация обязательных полей
            required_fields = ['symbol', 'quantity', 'order_type', 'side']
            for field in required_fields:
                if field not in data:
                    return jsonify({'error': f'Missing required field: {field}'}), 400
                    
            # Создаем ордер
            order = engine.create_order({
                'symbol': data['symbol'],
                'quantity': data['quantity'],
                'order_type': data['order_type'],
                'side': data['side'],
                'limit_price': data.get('limit_price'),
                'stop_price': data.get('stop_price'),
                'take_profit': data.get('take_profit'),
                'stop_loss': data.get('stop_loss'),
                'max_slippage': data.get('max_slippage', 0.5),
                'user_wallet': data.get('user_wallet', ''),
                'order_wallet': wallet_address,
                'entry_price': data.get('entry_price'),
                'trailing_type': data.get('trailing_type'),
                'trailing_distance': data.get('trailing_distance'),
                'oco_group_id': data.get('oco_group_id'),
                'oco_related_ids': data.get('oco_related_ids', []),
            })
            
            # Store wallet_id in order if needed for later reference
            if wallet_id:
                # Add wallet_id to the order's dictionary representation
                order_dict = order.to_dict()
                order_dict['order_wallet_id'] = wallet_id
                
            # Рассчитываем газ и комиссию для ордера
            from order_executor import calculate_order_gas_requirements
            gas_info = {}
            pair_pools = get_pair_pools(order.symbol)
            if pair_pools:
                primary_pool = pair_pools[0]
                # Создаем временную структуру для расчета газа
                temp_order = {
                    'amount': float(order.quantity),
                    'type': order.type.value.lower(),
                    'max_slippage': float(order.max_slippage),
                    'order_wallet': order.order_wallet
                }
                gas_info = calculate_order_gas_requirements(temp_order, primary_pool)
                
            response_data = {
                'success': True,
                'order': order.to_dict(),
                'message': f'Order {order.id} created successfully'
            }
            
            # Добавляем информацию о газе, если она доступна
            if gas_info.get('success'):
                response_data['gas_info'] = {
                    'gas_amount': gas_info['gas_amount'],
                    'total_amount': gas_info['total_amount'],
                    'from_token': gas_info['from_token'],
                    'to_token': gas_info['to_token'],
                    'from_amount': gas_info['from_amount'],
                    'expected_output': gas_info['expected_output'],
                    'dex': gas_info['dex']
                }
                
            return jsonify(response_data)
        except Exception as e:
            print(f"[API] Create order error: {e}")
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/orders', methods=['GET'])
    def api_v1_get_orders():
        """
        API для получения списка ордеров
        Параметры: user_wallet (опционально)
        """
        try:
            # Import inside function to avoid circular imports
            from app import load_orders
            
            user_wallet = request.args.get('user_wallet')
            orders_data = load_orders(user_wallet)
            
            return jsonify({
                'success': True,
                'orders': orders_data.get('orders', [])
            })
        except Exception as e:
            print(f"[API] Get orders error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/orders/<order_id>', methods=['GET'])
    def api_v1_get_order(order_id):
        """
        API для получения информации об ордере
        """
        try:
            # Import inside function to avoid circular imports
            from app import load_orders
            from order_engine import get_order_engine
            
            engine = get_order_engine()
            
            if order_id in engine.processor.orders:
                order = engine.processor.orders[order_id]
                return jsonify({
                    'success': True,
                    'order': order.to_dict()
                })
            else:
                # Пытаемся загрузить из БД
                orders_data = load_orders()
                order_dict = next((o for o in orders_data.get('orders', []) if o['id'] == order_id), None)
                if order_dict:
                    from order_engine import OrderEngine
                    order = OrderEngine._convert_legacy_order(order_dict)
                    if order:
                        return jsonify({
                            'success': True,
                            'order': order.to_dict()
                        })
                        
            return jsonify({'error': 'Order not found'}), 404
        except Exception as e:
            print(f"[API] Get order error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/orders/<order_id>', methods=['DELETE'])
    def api_v1_cancel_order(order_id):
        """
        API для отмены ордера
        """
        try:
            # Import inside function to avoid circular imports
            from app import (
                load_orders,
                save_order
            )
            from datetime import datetime
            
            orders_data = load_orders()
            
            for order in orders_data['orders']:
                if order['id'] == order_id and order['status'] in ('unfunded', 'waiting_entry', 'opened', 'active'):
                    order['status'] = 'cancelled'
                    order['cancelled_at'] = datetime.now().isoformat()
                    save_order(order)
                    return jsonify({
                        'success': True,
                        'message': 'Order cancelled'
                    })
                    
            return jsonify({'error': 'Order not found or already executed/cancelled'}), 404
        except Exception as e:
            print(f"[API] Cancel order error: {e}")
            return jsonify({'error': str(e)}), 500