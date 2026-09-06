
USE DATABASE analytics_agent_db;
USE SCHEMA raw;

CREATE OR REPLACE TABLE transactions (
    order_id            VARCHAR(20)     NOT NULL,
    order_date           DATE            NOT NULL,
    sales                NUMBER(12,2)    NOT NULL,
    quantity             NUMBER(4,0)     NOT NULL,
    discount             NUMBER(5,4)     NOT NULL,
    profit               NUMBER(12,2)    NOT NULL,
    region               VARCHAR(20)     NOT NULL,
    state                VARCHAR(50)     NOT NULL,
    city_type            VARCHAR(20)     NOT NULL,
    outlet_type          VARCHAR(20)     NOT NULL,
    category             VARCHAR(50)     NOT NULL,
    sub_category         VARCHAR(50)     NOT NULL,
    segment              VARCHAR(30)     NOT NULL,
    ship_mode            VARCHAR(30)     NOT NULL,
    PRIMARY KEY (order_id)
)
COMMENT = 'Anomaly-injected transaction data';
