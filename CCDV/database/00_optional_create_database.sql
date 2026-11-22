-- 00_optional_create_database.sql
-- Run ONLY if ai_travel_buddy does not already exist.
-- In pgAdmin: connect to maintenance database 'postgres' as an administrator.
-- PostgreSQL CREATE DATABASE must be run outside a transaction block.
-- You already created this database, so SKIP this file.

CREATE DATABASE ai_travel_buddy
    WITH OWNER = postgres
         ENCODING = 'UTF8';
