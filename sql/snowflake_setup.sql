CREATE OR REPLACE RESOURCE MONITOR analytics_agent_monitor
  WITH CREDIT_QUOTA = 50
  FREQUENCY = MONTHLY
  START_TIMESTAMP = IMMEDIATELY
  TRIGGERS
    ON 75 PERCENT DO NOTIFY
    ON 90 PERCENT DO SUSPEND
    ON 100 PERCENT DO SUSPEND_IMMEDIATE;


CREATE OR REPLACE WAREHOUSE analytics_agent_wh
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE
  RESOURCE_MONITOR = analytics_agent_monitor
  COMMENT = 'Warehouse for AI Business Analytics Agent project';


CREATE OR REPLACE DATABASE analytics_agent_db
  COMMENT = 'AI Business Analytics & Anomaly Detection Agent';

USE DATABASE analytics_agent_db;

CREATE OR REPLACE SCHEMA raw
  COMMENT = 'Raw loaded data, unmodified from source CSV';

CREATE OR REPLACE SCHEMA staging
  COMMENT = 'Cleaned, typed, deduplicated data';

CREATE OR REPLACE SCHEMA analytics
  COMMENT = 'KPI views, trend views, and other analytics-ready objects';

SHOW WAREHOUSES LIKE 'analytics_agent_wh';
SHOW RESOURCE MONITORS LIKE 'analytics_agent_monitor';
SHOW SCHEMAS IN DATABASE analytics_agent_db;