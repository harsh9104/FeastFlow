-- Runs once when the MySQL volume is first created. Separate DB for pytest.
CREATE DATABASE IF NOT EXISTS feastflow_test;
GRANT ALL ON feastflow_test.* TO 'feastflow'@'%';
