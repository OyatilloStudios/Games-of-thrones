-- ⚔️ Vesteros RPG MySQL sxemasi

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    telegram_id VARCHAR(50) PRIMARY KEY,
    username VARCHAR(100),
    house_id VARCHAR(50),
    role VARCHAR(50) DEFAULT 'citizen',
    wallet_balance DOUBLE DEFAULT 100,
    last_checkin DATE NULL,
    casino_spins_left INT DEFAULT 3,
    last_casino_spin_date DATE NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Houses Table
CREATE TABLE IF NOT EXISTS houses (
    house_id VARCHAR(50) PRIMARY KEY,
    house_name VARCHAR(100) NOT NULL,
    currency_name VARCHAR(100) NOT NULL,
    currency_symbol VARCHAR(10) NOT NULL,
    lord_id VARCHAR(50) DEFAULT '0',
    treasury_balance DOUBLE DEFAULT 500,
    wall_health INT DEFAULT 600,
    valyrian_steel_count INT DEFAULT 1,
    tax_rate DOUBLE DEFAULT 0.05,
    group_link VARCHAR(255) NULL,
    group_chat_id VARCHAR(50) NULL,
    defense_cooldown_until VARCHAR(100) NULL,
    wall_type VARCHAR(50) DEFAULT 'qora',
    wall_max_health INT DEFAULT 600,
    alliance_house_id VARCHAR(50) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Units Table
CREATE TABLE IF NOT EXISTS units (
    unit_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    cost_tanga DOUBLE NOT NULL,
    attack DOUBLE NOT NULL,
    defense DOUBLE NOT NULL,
    type VARCHAR(50) NOT NULL,
    special_effects TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. House Units (Army Ownership)
CREATE TABLE IF NOT EXISTS house_units (
    house_id VARCHAR(50),
    unit_id VARCHAR(50),
    quantity INT DEFAULT 0,
    PRIMARY KEY (house_id, unit_id),
    FOREIGN KEY (house_id) REFERENCES houses(house_id) ON DELETE CASCADE,
    FOREIGN KEY (unit_id) REFERENCES units(unit_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Bank Treasury Table
CREATE TABLE IF NOT EXISTS bank_treasury (
    id INT PRIMARY KEY AUTO_INCREMENT,
    total_bank_coins DOUBLE DEFAULT 10000,
    casino_revenue DOUBLE DEFAULT 0,
    banker_id VARCHAR(50) DEFAULT '0'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. Loans Table
CREATE TABLE IF NOT EXISTS loans (
    loan_id VARCHAR(50) PRIMARY KEY,
    house_id VARCHAR(50) NOT NULL,
    amount DOUBLE NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    requested_at VARCHAR(100) NULL,
    approved_at VARCHAR(100) NULL,
    FOREIGN KEY (house_id) REFERENCES houses(house_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. Broadcasts Table
CREATE TABLE IF NOT EXISTS broadcasts (
    broadcast_id VARCHAR(50) PRIMARY KEY,
    timestamp VARCHAR(100) NOT NULL,
    sender_id VARCHAR(50) NOT NULL,
    target_type VARCHAR(50) NOT NULL,
    message_text TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'sent'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8. Transactions Table
CREATE TABLE IF NOT EXISTS transactions (
    tx_id VARCHAR(50) PRIMARY KEY,
    timestamp VARCHAR(100) NOT NULL,
    from_id VARCHAR(50) NOT NULL,
    to_id VARCHAR(50) NOT NULL,
    amount DOUBLE NOT NULL,
    currency VARCHAR(20) NOT NULL,
    tx_type VARCHAR(50) NOT NULL,
    description TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 9. Battles Table
CREATE TABLE IF NOT EXISTS battles (
    battle_id VARCHAR(50) PRIMARY KEY,
    timestamp VARCHAR(100) NOT NULL,
    attacker_house VARCHAR(50) NOT NULL,
    defender_house VARCHAR(50) NOT NULL,
    attacker_troops_json TEXT NOT NULL,
    winner_house VARCHAR(50) NULL,
    attacker_casualties_json TEXT NULL,
    defender_casualties_json TEXT NULL,
    battle_log TEXT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    attacker_ally_house VARCHAR(50) NULL,
    attacker_ally_troops_json TEXT NULL,
    defender_ally_house VARCHAR(50) NULL,
    defender_ally_troops_json TEXT NULL,
    FOREIGN KEY (attacker_house) REFERENCES houses(house_id) ON DELETE CASCADE,
    FOREIGN KEY (defender_house) REFERENCES houses(house_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 10. Casino Broadcasts Table
CREATE TABLE IF NOT EXISTS casino_broadcasts (
    telegram_id VARCHAR(50) NOT NULL,
    message_id VARCHAR(50) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 11. Settings Table (Script properties replacement)
CREATE TABLE IF NOT EXISTS settings (
    setting_key VARCHAR(100) PRIMARY KEY,
    setting_value TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
