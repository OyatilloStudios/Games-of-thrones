import os
import csv
import pymysql
from dotenv import load_dotenv

load_dotenv()

# MySQL Database configuration from environment variables
DB_HOST = os.getenv('MYSQLHOST') or os.getenv('DB_HOST') or 'localhost'
DB_USER = os.getenv('MYSQLUSER') or os.getenv('DB_USER') or 'root'
DB_PASSWORD = os.getenv('MYSQLPASSWORD') or os.getenv('DB_PASSWORD') or ''
DB_NAME = os.getenv('MYSQLDATABASE') or os.getenv('DB_NAME') or 'vesteros_rpg'
DB_PORT = int(os.getenv('MYSQLPORT') or os.getenv('DB_PORT') or '3306')

TABLES = [
    {
        'name': 'houses',
        'file': 'Houses',
        'columns': ['house_id', 'house_name', 'currency_name', 'currency_symbol', 'lord_id', 'treasury_balance', 'wall_health', 'valyrian_steel_count', 'tax_rate', 'group_link', 'group_chat_id', 'defense_cooldown_until', 'wall_type', 'wall_max_health', 'alliance_house_id']
    },
    {
        'name': 'users',
        'file': 'Users',
        'columns': ['telegram_id', 'username', 'house_id', 'role', 'wallet_balance', 'last_checkin', 'casino_spins_left', 'last_casino_spin_date']
    },
    {
        'name': 'units',
        'file': 'Units',
        'columns': ['unit_id', 'name', 'cost_tanga', 'attack', 'defense', 'type', 'special_effects']
    },
    {
        'name': 'house_units',
        'file': 'House_Units',
        'columns': ['house_id', 'unit_id', 'quantity']
    },
    {
        'name': 'bank_treasury',
        'file': 'Bank_Treasury',
        'columns': ['total_bank_coins', 'casino_revenue', 'banker_id']
    },
    {
        'name': 'loans',
        'file': 'Loans',
        'columns': ['loan_id', 'house_id', 'amount', 'status', 'requested_at', 'approved_at']
    },
    {
        'name': 'broadcasts',
        'file': 'Broadcasts',
        'columns': ['broadcast_id', 'timestamp', 'sender_id', 'target_type', 'message_text', 'status']
    },
    {
        'name': 'transactions',
        'file': 'Transactions',
        'columns': ['tx_id', 'timestamp', 'from_id', 'to_id', 'amount', 'currency', 'tx_type', 'description']
    },
    {
        'name': 'battles',
        'file': 'Battles',
        'columns': ['battle_id', 'timestamp', 'attacker_house', 'defender_house', 'attacker_troops_json', 'winner_house', 'attacker_casualties_json', 'defender_casualties_json', 'battle_log', 'status', 'attacker_ally_house', 'attacker_ally_troops_json', 'defender_ally_house', 'defender_ally_troops_json']
    },
    {
        'name': 'casino_broadcasts',
        'file': 'Casino_Broadcasts',
        'columns': ['telegram_id', 'message_id']
    }
]

# Helper to search for CSV files in multiple paths
def find_csv_file(file_name):
    possible_names = [
        f"{file_name}.csv",
        f"GOT - {file_name}.csv",
        f"got - {file_name}.csv"
    ]
    possible_dirs = [
        '.',
        '../heets',
        'heets',
        '../'
    ]
    for directory in possible_dirs:
        for name in possible_names:
            path = os.path.join(directory, name)
            if os.path.exists(path):
                return os.path.abspath(path)
    return None

# Clean value logic before writing to database
def clean_value(val, col_name, table_name):
    if val is None:
        if col_name in ['attack', 'defense', 'cost_tanga', 'treasury_balance', 'wall_health', 'valyrian_steel_count', 'tax_rate', 'wallet_balance', 'casino_spins_left', 'amount', 'quantity']:
            return 0
        if col_name == 'type' and table_name == 'units':
            return 'item'
        return None
        
    s_val = str(val).strip()
    
    # Convert decimal commas like "0,05" to "0.05"
    if ',' in s_val and s_val.replace(',', '').replace('-', '').isdigit():
        s_val = s_val.replace(',', '.')
        
    if col_name in ['attack', 'defense', 'cost_tanga', 'treasury_balance', 'wall_health', 'valyrian_steel_count', 'tax_rate', 'wallet_balance', 'casino_spins_left', 'amount', 'quantity']:
        if s_val == '':
            return 0
        try:
            return float(s_val) if '.' in s_val or col_name in ['tax_rate', 'treasury_balance', 'wallet_balance', 'amount'] else int(float(s_val))
        except ValueError:
            return 0
            
    if s_val == '':
        if col_name == 'type' and table_name == 'units':
            return 'item'
        if col_name in ['battle_log', 'attacker_troops_json']:
            return '{}'
        return None
        
    return s_val

def run_migration():
    print("[INFO] Connecting to MySQL Database...")
    conn = pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        port=DB_PORT,
        charset='utf8mb4',
        autocommit=True
    )
    
    try:
        with conn.cursor() as cursor:
            # Disable foreign key checks for clean truncation/deletion
            cursor.execute('SET FOREIGN_KEY_CHECKS = 0')
            
            schema_path = 'schema.sql'
            if os.path.exists(schema_path):
                print("[INFO] Loading MySQL schema (schema.sql)...")
                with open(schema_path, 'r', encoding='utf-8') as f:
                    schema_sql = f.read()
                
                statements = schema_sql.split(';')
                for stmt in statements:
                    # Filter comments and whitespace
                    lines = stmt.split('\n')
                    clean_lines = [line for line in lines if not line.strip().startswith('--')]
                    stmt_clean = '\n'.join(clean_lines).strip()
                    if stmt_clean:
                        cursor.execute(stmt_clean)
                print("[SUCCESS] Database schema initialized.")
            else:
                print("[WARNING] schema.sql not found!")

            for table in TABLES:
                csv_path = find_csv_file(table['file'])
                if not csv_path:
                    print(f"[WARNING] CSV file for {table['file']} not found. Skipping.")
                    continue
                
                print(f"[INFO] Reading {os.path.basename(csv_path)}...")
                
                rows_to_insert = []
                with open(csv_path, 'r', encoding='utf-8') as f:
                    # Detect delimiter
                    sample = f.read(2048)
                    f.seek(0)
                    delimiter = ','
                    if ';' in sample and sample.count(';') > sample.count(','):
                        delimiter = ';'
                    
                    reader = csv.reader(f, delimiter=delimiter)
                    # Skip header row
                    next(reader, None)
                    
                    for row in reader:
                        # Map row values to columns by index
                        row_vals = []
                        for idx, col in enumerate(table['columns']):
                            val = row[idx] if idx < len(row) else None
                            row_vals.append(clean_value(val, col, table['name']))
                        rows_to_insert.append(row_vals)
                
                # Delete existing records in the table
                cursor.execute(f"DELETE FROM {table['name']}")
                
                if not rows_to_insert:
                    print(f"[INFO] Table '{table['name']}' has no records to seed.")
                    continue
                
                # Build INSERT IGNORE query
                cols_str = ', '.join(table['columns'])
                placeholders = ', '.join(['%s'] * len(table['columns']))
                insert_query = f"INSERT IGNORE INTO {table['name']} ({cols_str}) VALUES ({placeholders})"
                
                # Chunked bulk insert
                chunk_size = 500
                inserted_count = 0
                for i in range(0, len(rows_to_insert), chunk_size):
                    chunk = rows_to_insert[i:i + chunk_size]
                    cursor.executemany(insert_query, chunk)
                    inserted_count += len(chunk)
                
                print(f"[SUCCESS] Loaded {inserted_count} rows into '{table['name']}' table.")
                
            cursor.execute('SET FOREIGN_KEY_CHECKS = 1')
            print("[SUCCESS] Database migration and CSV seeding completed successfully!")
            
    except Exception as e:
        print(f"[ERROR] Error during database migration: {e}")
        raise e
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
