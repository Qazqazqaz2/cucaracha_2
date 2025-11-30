#!/usr/bin/env python3
"""
Script to list all API v1 routes
"""

def list_api_routes():
    """List all API v1 routes"""
    try:
        import app
        routes = [rule.rule for rule in app.app.url_map.iter_rules() if rule.rule.startswith('/api/v1')]
        print("Доступные API v1 маршруты:")
        for route in sorted(routes):
            print(f"  - {route}")
        print(f"\nВсего маршрутов: {len(routes)}")
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    list_api_routes()