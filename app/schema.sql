-- TCC V1 Spine Schema
-- 8 tables: users, products, product_versions, clients,
--            sales, payments, receipts, activity_log

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name               TEXT    NOT NULL,
    email                   TEXT    NOT NULL UNIQUE,
    password_hash           TEXT    NOT NULL,
    manager_password_hash   TEXT    NOT NULL,
    role                    TEXT    NOT NULL CHECK(role IN (
                                'super_admin', 'administrator',
                                'finance_officer', 'technical_officer',
                                'marketing_manager'
                            )),
    status                  TEXT    NOT NULL DEFAULT 'active'
                                CHECK(status IN ('active', 'inactive')),
    created_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at              DATETIME
);

CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    category        TEXT    NOT NULL CHECK(category IN (
                        'school_management', 'library', 'website',
                        'mobile_app', 'desktop_app', 'api',
                        'custom_software', 'other'
                    )),
    description     TEXT,
    date_created    DATE,
    launch_date     DATE,
    current_version TEXT,
    status          TEXT    NOT NULL DEFAULT 'active'
                        CHECK(status IN ('active', 'inactive', 'deprecated')),
    tech_stack      TEXT,
    license_number  TEXT,
    support_contact TEXT,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at      DATETIME
);

CREATE TABLE IF NOT EXISTS product_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER NOT NULL REFERENCES products(id),
    version_number  TEXT    NOT NULL,
    release_date    DATE,
    changelog       TEXT,
    bug_fixes       TEXT,
    new_features    TEXT,
    developer_notes TEXT,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clients (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    organization    TEXT,
    phone           TEXT,
    email           TEXT,
    country         TEXT,
    address         TEXT,
    date_registered DATE    NOT NULL DEFAULT CURRENT_DATE,
    contract_info   TEXT,
    notes           TEXT,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at      DATETIME
);

-- agent_id reserved NULL for V1.2
CREATE TABLE IF NOT EXISTS sales (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER NOT NULL REFERENCES products(id),
    client_id       INTEGER NOT NULL REFERENCES clients(id),
    agent_id        INTEGER,
    sale_date       DATE    NOT NULL DEFAULT CURRENT_DATE,
    sale_amount     INTEGER NOT NULL CHECK(sale_amount >= 0),
    discount        INTEGER NOT NULL DEFAULT 0 CHECK(discount >= 0),
    payment_method  TEXT    NOT NULL CHECK(payment_method IN (
                        'cash', 'bank_transfer', 'mobile_money', 'cheque', 'other'
                    )),
    notes           TEXT,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at      DATETIME
);

-- Instalment payments — amount_paid and balance are COMPUTED from this table,
-- never stored on the sale row itself.
CREATE TABLE IF NOT EXISTS payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id         INTEGER NOT NULL REFERENCES sales(id),
    amount          INTEGER NOT NULL CHECK(amount > 0),
    payment_date    DATE    NOT NULL DEFAULT CURRENT_DATE,
    payment_method  TEXT    NOT NULL CHECK(payment_method IN (
                        'cash', 'bank_transfer', 'mobile_money', 'cheque', 'other'
                    )),
    notes           TEXT,
    recorded_by     INTEGER NOT NULL REFERENCES users(id),
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS receipts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_number  TEXT    NOT NULL UNIQUE,
    sale_id         INTEGER NOT NULL REFERENCES sales(id),
    issue_date      DATE    NOT NULL DEFAULT CURRENT_DATE,
    amount          INTEGER NOT NULL,
    qr_payload      TEXT    NOT NULL,
    pdf_path        TEXT,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Dual-purpose: dashboard recent-activity feed + full audit trail
CREATE TABLE IF NOT EXISTS activity_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id),
    action      TEXT    NOT NULL,
    entity_type TEXT,
    entity_id   INTEGER,
    ip_address  TEXT,
    details     TEXT,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
