"""
Main API routes module - registers all API endpoints
"""

def register_all_routes(app):
    """
    Register all API routes with the Flask application
    """
    # Import inside function to avoid circular imports
    from api.trading import register_trading_routes
    from api.wallets import register_wallets_routes
    from api.orders import register_orders_routes
    from api.market_data import register_market_data_routes
    
    register_trading_routes(app)
    register_wallets_routes(app)
    register_orders_routes(app)
    register_market_data_routes(app)