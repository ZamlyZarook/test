-- Users table for authentication
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    role ENUM('admin', 'merchant') NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP NULL,
    is_active BOOLEAN DEFAULT TRUE
);

-- Merchants table
CREATE TABLE IF NOT EXISTS merchants (
    id INT AUTO_INCREMENT PRIMARY KEY,
    merchant_code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    address TEXT NOT NULL,
    country VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    website VARCHAR(255),
    contact_number VARCHAR(20),
    note TEXT,
    user_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Schemes table
CREATE TABLE IF NOT EXISTS schemes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    scheme_id VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    valid_countries JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    validity_end_date DATE NOT NULL,
    total_coupons_allowed INT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);

-- Coupons table
CREATE TABLE IF NOT EXISTS coupons (
    id INT AUTO_INCREMENT PRIMARY KEY,
    coupon_code VARCHAR(10) UNIQUE NOT NULL,
    qr_code_path VARCHAR(255) NOT NULL,
    scheme_id INT NOT NULL,
    validity_date DATE NOT NULL,
    image_path VARCHAR(255),
    status ENUM('generated', 'issued', 'redeemed', 'expired') DEFAULT 'generated',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (scheme_id) REFERENCES schemes(id) ON DELETE CASCADE
);

-- Coupon issues table
CREATE TABLE IF NOT EXISTS coupon_issues (
    id INT AUTO_INCREMENT PRIMARY KEY,
    merchant_id INT NOT NULL,
    scheme_id INT NOT NULL,
    issued_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    number_of_coupons INT NOT NULL,
    status ENUM('active', 'completed', 'cancelled') DEFAULT 'active',
    FOREIGN KEY (merchant_id) REFERENCES merchants(id) ON DELETE CASCADE,
    FOREIGN KEY (scheme_id) REFERENCES schemes(id) ON DELETE CASCADE
);

-- Coupon redemptions table
CREATE TABLE IF NOT EXISTS redemptions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    coupon_id INT NOT NULL,
    merchant_id INT NOT NULL,
    redemption_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (coupon_id) REFERENCES coupons(id) ON DELETE CASCADE,
    FOREIGN KEY (merchant_id) REFERENCES merchants(id) ON DELETE CASCADE
);

-- Revenue table
CREATE TABLE IF NOT EXISTS revenue (
    id INT AUTO_INCREMENT PRIMARY KEY,
    scheme_id INT NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (scheme_id) REFERENCES schemes(id) ON DELETE CASCADE
);

-- Create indexes for better performance
CREATE INDEX idx_coupon_status ON coupons(status);
CREATE INDEX idx_merchant_status ON merchants(is_active);
CREATE INDEX idx_scheme_status ON schemes(is_active);
CREATE INDEX idx_redemption_date ON redemptions(redemption_date);
CREATE INDEX idx_revenue_date ON revenue(transaction_date); 

