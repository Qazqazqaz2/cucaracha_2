"""
Market Data API endpoints (Pairs, Tokens, Quotes)
"""
from flask import request, jsonify
import traceback

def register_market_data_routes(app):
    """Register market data API routes with the Flask app"""
    
    @app.route('/api/v1/pairs', methods=['GET'])
    def api_v1_get_pairs():
        """
        API для получения информации о всех торговых парах
        """
        try:
            # Import inside function to avoid circular imports
            from app import (
                pools,
                get_pair_pools,
                get_current_price
            )
            
            pairs_info = {}
            for pair_name, pair_pools in pools.items():
                pair_info = {
                    'name': pair_name,
                    'pools': [],
                    'current_price': 0
                }
                
                for pool in pair_pools:
                    price = get_current_price(pool['address'], pool)
                    if price > pair_info['current_price']:
                        pair_info['current_price'] = price
                        
                    pair_info['pools'].append({
                        'address': pool['address'],
                        'dex': pool['dex'],
                        'from_token': pool['from_token'],
                        'to_token': pool['to_token'],
                        'from_token_address': pool.get('from_token_address'),
                        'to_token_address': pool.get('to_token_address'),
                        'from_decimals': pool.get('from_decimals', 9),
                        'to_decimals': pool.get('to_decimals', 6),
                        'price': price
                    })
                    
                pairs_info[pair_name] = pair_info
                
            return jsonify({
                'success': True,
                'pairs': pairs_info
            })
        except Exception as e:
            print(f"[API] Get pairs error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/pairs/<pair_name>', methods=['GET'])
    def api_v1_get_pair(pair_name):
        """
        API для получения информации о конкретной торговой паре
        """
        try:
            # Import inside function to avoid circular imports
            from app import (
                get_pair_pools,
                get_current_price
            )
            
            pair_pools = get_pair_pools(pair_name)
            if not pair_pools:
                return jsonify({'error': f'Pair {pair_name} not found'}), 404
                
            pair_info = {
                'name': pair_name,
                'pools': [],
                'current_price': 0
            }
            
            for pool in pair_pools:
                price = get_current_price(pool['address'], pool)
                if price > pair_info['current_price']:
                    pair_info['current_price'] = price
                    
                pair_info['pools'].append({
                    'address': pool['address'],
                    'dex': pool['dex'],
                    'from_token': pool['from_token'],
                    'to_token': pool['to_token'],
                    'from_token_address': pool.get('from_token_address'),
                    'to_token_address': pool.get('to_token_address'),
                    'from_decimals': pool.get('from_decimals', 9),
                    'to_decimals': pool.get('to_decimals', 6),
                    'price': price
                })
                
            return jsonify({
                'success': True,
                'pair': pair_info
            })
        except Exception as e:
            print(f"[API] Get pair error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/tokens', methods=['GET'])
    def api_v1_get_tokens():
        """
        API для получения информации о всех токенах
        """
        try:
            # Import inside function to avoid circular imports
            from app import pools
            
            tokens = set()
            for pair_name, pair_pools in pools.items():
                for pool in pair_pools:
                    tokens.add(pool['from_token'])
                    tokens.add(pool['to_token'])
                    
            return jsonify({
                'success': True,
                'tokens': list(tokens)
            })
        except Exception as e:
            print(f"[API] Get tokens error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/quote', methods=['GET'])
    def api_v1_get_quote():
        """
        API для получения котировки обмена
        Параметры: pair, amount, slippage (опционально)
        """
        try:
            # Import inside function to avoid circular imports
            from app import (
                get_pair_pools,
                compute_swap_quote,
                DEFAULT_SLIPPAGE
            )
            
            pair = request.args.get('pair', 'TON-USDT')
            amount = float(request.args.get('amount', 1))
            slippage = float(request.args.get('slippage', DEFAULT_SLIPPAGE))
            
            pair_pools = get_pair_pools(pair)
            if not pair_pools:
                return jsonify({'error': f'No pools found for pair {pair}'}), 404
                
            quotes = []
            for pool in pair_pools:
                quote_result = compute_swap_quote(pool, amount, slippage)
                if quote_result:
                    quotes.append({
                        'dex': pool['dex'],
                        'pool_address': pool['address'],
                        'output': quote_result['output'],
                        'min_output': quote_result['min_output'],
                        'price': quote_result['price'],
                        'from_token': pool['from_token'],
                        'to_token': pool['to_token']
                    })
                    
            if not quotes:
                return jsonify({'error': 'Unable to calculate quote'}), 500
                
            best_quote = max(quotes, key=lambda x: x['output'])
            
            return jsonify({
                'success': True,
                'pair': pair,
                'amount': amount,
                'slippage': slippage,
                'best_quote': best_quote,
                'all_quotes': quotes
            })
        except Exception as e:
            print(f"[API] Get quote error: {e}")
            return jsonify({'error': str(e)}), 500