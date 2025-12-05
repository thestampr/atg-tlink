CREATE TABLE IF NOT EXISTS users (
    id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL PRIMARY KEY DEFAULT (UUID()),
    parent_user_id VARCHAR(191),
    username VARCHAR(50) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    display_name VARCHAR(191),
    email VARCHAR(100) NOT NULL,
    role ENUM('admin','operator','viewer') DEFAULT 'viewer',
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_users_username (username),
    UNIQUE KEY uq_users_email (email),
    KEY idx_users_email (email),
    KEY idx_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

ALTER TABLE users
    MODIFY COLUMN id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL;

CREATE TABLE IF NOT EXISTS devices (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    external_id BIGINT NOT NULL UNIQUE,
    parent_user_id VARCHAR(191),
    user_id CHAR(36),
    device_name VARCHAR(191),
    device_no VARCHAR(191),
    group_id BIGINT,
    lat VARCHAR(64),
    lng VARCHAR(64),
    product_id VARCHAR(191),
    product_type VARCHAR(191),
    protocol_label VARCHAR(191),
    last_flag VARCHAR(32),
    last_raw_payload LONGTEXT,
    last_push_time DATETIME,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_devices_user_id (user_id),
    CONSTRAINT fk_devices_users FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE devices
    MODIFY COLUMN user_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL;

CREATE TABLE IF NOT EXISTS sensors (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    external_id BIGINT NOT NULL,
    device_id BIGINT UNSIGNED NOT NULL,
    sensor_type_id INT,
    is_line TINYINT(1),
    unit VARCHAR(64),
    latest_value VARCHAR(255),
    latest_recorded_at DATETIME,
    is_alarm TINYINT(1),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_sensor_device (device_id, external_id),
    KEY idx_sensors_device_id (device_id),
    CONSTRAINT fk_sensors_devices FOREIGN KEY (device_id) REFERENCES devices(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sensor_readings (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    sensor_id BIGINT UNSIGNED NOT NULL,
    recorded_at DATETIME NOT NULL,
    sensor_timestamp VARCHAR(64),
    is_alarm TINYINT(1),
    is_line TINYINT(1),
    raw_value VARCHAR(255),
    scaled_value VARCHAR(255),
    raw_payload LONGTEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_sensor_record (sensor_id, recorded_at, sensor_timestamp),
    KEY idx_sensor_readings_sensor_id (sensor_id),
    CONSTRAINT fk_sensor_readings_sensor FOREIGN KEY (sensor_id) REFERENCES sensors(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    setting_key VARCHAR(100) NOT NULL,
    setting_value LONGTEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_settings_key (setting_key),
    CONSTRAINT chk_settings_value_json CHECK (JSON_VALID(setting_value))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL PRIMARY KEY DEFAULT (UUID()),
    user_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
    token VARCHAR(500) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_refresh_tokens_user_id (user_id),
    KEY idx_refresh_tokens_token (token(255)),
    CONSTRAINT fk_refresh_tokens_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE refresh_tokens
    MODIFY COLUMN id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
    MODIFY COLUMN user_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL;

CREATE TABLE IF NOT EXISTS tanks (
    id CHAR(36) NOT NULL PRIMARY KEY DEFAULT (UUID()),
    sensor_id BIGINT UNSIGNED,
    name VARCHAR(100) NOT NULL,
    fuel_type VARCHAR(50) NOT NULL,
    capacity DECIMAL(10,2) NOT NULL,
    current_volume DECIMAL(10,2) DEFAULT 0.00,
    temperature DECIMAL(5,2) DEFAULT 0.00,
    water_level DECIMAL(5,2) DEFAULT 0.00,
    status ENUM('normal','low','warning','critical') DEFAULT 'normal',
    location VARCHAR(100),
    install_date DATE,
    maintenance_date DATE,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_tanks_status (status),
    KEY idx_tanks_fuel_type (fuel_type),
    KEY idx_tanks_active (is_active),
    KEY idx_tanks_sensor_id (sensor_id),
    CONSTRAINT fk_tanks_sensor FOREIGN KEY (sensor_id) REFERENCES sensors(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS alarms (
    id CHAR(36) NOT NULL PRIMARY KEY DEFAULT (UUID()),
    tank_id CHAR(36) NOT NULL,
    tank_name VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL,
    severity ENUM('info','medium','warning','high','critical') DEFAULT 'info',
    message TEXT NOT NULL,
    timestamp TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    is_acknowledged TINYINT(1) DEFAULT 0,
    acknowledged_by VARCHAR(100),
    acknowledged_at TIMESTAMP NULL DEFAULT NULL,
    resolved_at TIMESTAMP NULL DEFAULT NULL,
    metadata LONGTEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_alarms_tank_id (tank_id),
    KEY idx_alarms_severity (severity),
    KEY idx_alarms_acknowledged (is_acknowledged),
    KEY idx_alarms_timestamp (timestamp),
    CONSTRAINT chk_alarms_metadata_json CHECK (JSON_VALID(metadata)),
    CONSTRAINT fk_alarms_tank FOREIGN KEY (tank_id) REFERENCES tanks(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS transactions (
    id CHAR(36) NOT NULL PRIMARY KEY DEFAULT (UUID()),
    tank_id CHAR(36) NOT NULL,
    type ENUM('delivery','sales') NOT NULL,
    volume DECIMAL(10,2) NOT NULL,
    start_volume DECIMAL(10,2),
    end_volume DECIMAL(10,2),
    timestamp TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    duration INT,
    operator VARCHAR(100),
    notes TEXT,
    invoice_number VARCHAR(50),
    supplier VARCHAR(100),
    approved TINYINT(1) DEFAULT 0,
    approved_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_transactions_tank_id (tank_id),
    KEY idx_transactions_type (type),
    KEY idx_transactions_timestamp (timestamp),
    CONSTRAINT fk_transactions_tank FOREIGN KEY (tank_id) REFERENCES tanks(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
