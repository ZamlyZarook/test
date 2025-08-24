02/05/2025

CREATE TABLE invoice_headers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    invoice_number VARCHAR(20) NOT NULL UNIQUE,
    invoice_date DATE NOT NULL DEFAULT CURRENT_DATE,
    narration TEXT,
    ship_doc_entry_id INT NOT NULL,
    customer_id INT NOT NULL,
    company_id INT NOT NULL,
    payment_status INT DEFAULT 0,
    total FLOAT NOT NULL DEFAULT 0,
    created_by INT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (ship_doc_entry_id) REFERENCES ship_document_entry_master(id),
    FOREIGN KEY (customer_id) REFERENCES customer(id),
    FOREIGN KEY (company_id) REFERENCES company_info(id),
    FOREIGN KEY (created_by) REFERENCES user(id)
);

CREATE TABLE invoice_details (
    id INT AUTO_INCREMENT PRIMARY KEY,
    invoice_header_id INT NOT NULL,
    expense_id INT NOT NULL,
    description TEXT,
    original_amount FLOAT NOT NULL,
    margin FLOAT DEFAULT 0,
    original_chargeable_amount FLOAT,
    final_amount FLOAT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    settlement_id INT,
    FOREIGN KEY (invoice_header_id) REFERENCES invoice_headers(id),
    FOREIGN KEY (expense_id) REFERENCES shipment_expenses(id),
    FOREIGN KEY (settlement_id) REFERENCES expense_settlements(id)
);

CREATE TABLE expense_settlements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    expense_id INT NOT NULL,
    invoice_id INT NOT NULL,
    shipment_id INT NOT NULL,
    amount_charged FLOAT NOT NULL,
    created_by INT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (expense_id) REFERENCES shipment_expenses(id),
    FOREIGN KEY (invoice_id) REFERENCES invoice_headers(id),
    FOREIGN KEY (shipment_id) REFERENCES ship_document_entry_master(id),
    FOREIGN KEY (created_by) REFERENCES user(id)
);

ALTER TABLE shipment_expenses
ADD COLUMN margin FLOAT NULL,
ADD COLUMN chargeable_amount FLOAT NULL,
ADD COLUMN payment_status INT NULL;


ALTER TABLE shipment_expenses
ADD COLUMN document_number VARCHAR(100) NULL,
ADD COLUMN supplier_name VARCHAR(255) NULL,
ADD COLUMN value_amount FLOAT NULL,
ADD COLUMN vat_amount FLOAT NULL,
ADD COLUMN margin_amount FLOAT NULL,
ADD COLUMN attachment_visible_to_customer BOOLEAN NULL;


ALTER TABLE invoice_details
ADD COLUMN settlement_id INT NULL,
ADD CONSTRAINT fk_invoice_details_settlement_id
    FOREIGN KEY (settlement_id)
    REFERENCES expense_settlements(id);

ALTER TABLE shipment_expenses
ADD COLUMN charged_amount FLOAT NOT NULL,
ADD COLUMN balance_amount FLOAT NULL;

ALTER TABLE order_shipment
ADD COLUMN company_id INT NOT NULL,
ADD CONSTRAINT fk_order_shipment_company_id
    FOREIGN KEY (company_id)
    REFERENCES company_info(id);

13/05/2025

ALTER TABLE ship_cat_document
ADD COLUMN confidence_level FLOAT NOT NULL DEFAULT 0.0;


15/05/2025

ALTER TABLE ship_cat_document
ADD COLUMN content_similarity FLOAT NOT NULL DEFAULT 0.0,
ADD COLUMN ai_validate INT NOT NULL DEFAULT 0,
ADD COLUMN multiple_document INT NOT NULL DEFAULT 0;

