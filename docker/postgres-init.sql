-- One Postgres server, a separate database per service (logical isolation).
-- Runs once, on first init of an empty data volume.
CREATE DATABASE identity;
CREATE DATABASE panels;
CREATE DATABASE design;
CREATE DATABASE registry;
