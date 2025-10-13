import sqlite3

# Connect to the database
conn = sqlite3.connect('tokens.db')
cursor = conn.cursor()

# Query for the specific token
cursor.execute("SELECT symbol, name, display_name FROM tokens WHERE contract_address = 'EQCHh15TWQYA50Y5-K_60wt74aE4UVHlDSx-8meaCXTaMmQO'")
result = cursor.fetchone()

if result:
    print(f"Token info: symbol='{result[0]}', name='{result[1]}', display_name='{result[2]}'")
else:
    print("Token not found in database")

conn.close()