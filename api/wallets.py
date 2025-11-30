"""
Wallets API endpoints
"""
from flask import request, jsonify
import traceback
from datetime import datetime

def register_wallets_routes(app):
    """Register wallets API routes with the Flask app"""
    
    @app.route('/api/v1/wallets', methods=['GET'])
    def api_v1_get_wallets():
        """
        API для получения списка кошельков пользователя
        Параметры: owner_wallet (опционально)
        """
        try:
            # Import inside function to avoid circular imports
            from app import get_order_wallets
            
            owner_wallet = request.args.get('owner_wallet')
            wallets = get_order_wallets(owner_wallet)
            
            return jsonify({
                'success': True,
                'wallets': wallets
            })
        except Exception as e:
            print(f"[API] Get wallets error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/wallets', methods=['POST'])
    def api_v1_create_wallet():
        """
        API для создания нового кошелька
        Требуется: owner_wallet, address
        Опционально: label, mnemonic
        """
        try:
            # Import inside function to avoid circular imports
            from app import (
                get_order_wallet_record,
                get_db_connection,
                validate_address,
                encrypt_secret
            )
            
            data = request.json or {}
            owner_wallet = data.get('owner_wallet')
            address_raw = data.get('address')
            label = data.get('label')
            mnemonic = data.get('mnemonic')
            
            if not address_raw:
                return jsonify({'error': 'address is required'}), 400
                
            try:
                address = validate_address(address_raw)
            except Exception as e:
                return jsonify({'error': f'Invalid address: {e}'}), 400
                
            encrypted = None
            if mnemonic:
                try:
                    encrypted = encrypt_secret(mnemonic.strip())
                except RuntimeError as e:
                    return jsonify({'error': str(e)}), 400
                    
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO order_wallets (owner_wallet, address, label, encrypted_mnemonic)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (address) DO UPDATE SET
                            owner_wallet = EXCLUDED.owner_wallet,
                            label = EXCLUDED.label,
                            encrypted_mnemonic = COALESCE(EXCLUDED.encrypted_mnemonic, order_wallets.encrypted_mnemonic),
                            updated_at = NOW()
                        RETURNING id, owner_wallet, address, label, created_at, updated_at,
                                  encrypted_mnemonic IS NOT NULL AS has_mnemonic
                    """, (owner_wallet, address, label, encrypted))
                    row = cur.fetchone()
                    conn.commit()
                    if row:
                        wallet = dict(row)
                        wallet['label'] = wallet.get('label') or f"Wallet #{wallet['id']}"
                        if isinstance(wallet.get('created_at'), datetime):
                            wallet['created_at'] = wallet['created_at'].isoformat()
                        if isinstance(wallet.get('updated_at'), datetime):
                            wallet['updated_at'] = wallet['updated_at'].isoformat()
                        return jsonify({
                            'success': True,
                            'wallet': wallet
                        })
                        
            return jsonify({'error': 'Failed to create wallet'}), 500
        except Exception as e:
            print(f"[API] Create wallet error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/wallets/<int:wallet_id>', methods=['GET'])
    def api_v1_get_wallet(wallet_id: int):
        """
        API для получения информации о конкретном кошельке
        """
        try:
            # Import inside function to avoid circular imports
            from app import get_order_wallet_record
            
            wallet = get_order_wallet_record(wallet_id)
            if not wallet:
                return jsonify({'error': 'Wallet not found'}), 404
                
            return jsonify({
                'success': True,
                'wallet': wallet
            })
        except Exception as e:
            print(f"[API] Get wallet error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/wallets/<int:wallet_id>/balances', methods=['GET'])
    def api_v1_get_wallet_balances(wallet_id: int):
        """
        API для получения балансов кошелька
        """
        try:
            # Import inside function to avoid circular imports
            from app import (
                get_order_wallet_record,
                get_wallet_token_balances,
                get_balance
            )
            
            wallet = get_order_wallet_record(wallet_id)
            if not wallet:
                return jsonify({'error': 'Wallet not found'}), 404
                
            address = wallet['address']
            return jsonify({
                'success': True,
                'address': address,
                'tokens': get_wallet_token_balances(address),
                'balance': get_balance(address)
            })
        except Exception as e:
            print(f"[API] Get wallet balances error: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/v1/wallets/<int:wallet_id>/transfer', methods=['POST'])
    def api_v1_wallet_transfer(wallet_id: int):
        """
        API для перевода средств с кошелька
        Требуется: destination, amount
        Опционально: comment, token
        """
        try:
            # Import inside function to avoid circular imports
            from app import (
                get_order_wallet_record,
                get_order_wallet_credentials,
                transfer_ton_from_wallet
            )
            
            wallet = get_order_wallet_record(wallet_id)
            if not wallet:
                return jsonify({'error': 'Wallet not found'}), 404
                
            data = request.json or {}
            destination = data.get('destination')
            amount = float(data.get('amount', 0))
            comment = data.get('comment')
            token = data.get('token', 'TON').upper()
            
            if token != 'TON':
                return jsonify({'error': 'Only TON transfers are supported'}), 400
            if not destination or amount <= 0:
                return jsonify({'error': 'Specify recipient and amount'}), 400
                
            creds = get_order_wallet_credentials({'order_wallet_id': wallet_id, 'order_wallet': wallet['address']})
            if not creds or not creds.get('mnemonic'):
                return jsonify({'error': 'Wallet mnemonic not found'}), 400
                
            transfer_result = transfer_ton_from_wallet(creds, destination, amount, comment)
            return jsonify({
                'success': transfer_result.get('success', False),
                'result': transfer_result
            })
        except Exception as e:
            print(f"[API] Wallet transfer error: {e}")
            return jsonify({'error': str(e)}), 500