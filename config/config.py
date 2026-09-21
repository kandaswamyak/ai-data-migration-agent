"""
Configuration for AI Data Migration Agent

Set environment variables or update values here.
"""

import os


class Config:

    # Target database
    TARGET_DATABASE = "Azure SQL"

    # ========== ORACLE DATABASE SETTINGS ==========
    ORACLE_HOST = os.getenv("ORACLE_HOST", "localhost")
    ORACLE_PORT = int(os.getenv("ORACLE_PORT", "1521"))
    ORACLE_SERVICE_NAME = os.getenv("ORACLE_SERVICE_NAME", "ORCL")
    ORACLE_SID = os.getenv("ORACLE_SID", "")
    ORACLE_USERNAME = os.getenv("ORACLE_USERNAME", "")
    ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "")
    ORACLE_MODE = os.getenv("ORACLE_MODE", "AUTO")
    ORACLE_THICK_MODE = os.getenv("ORACLE_THICK_MODE", "false").lower() == "true"
    ORACLE_CLIENT_LIB_DIR = os.getenv("ORACLE_CLIENT_LIB_DIR", "")
    ORACLE_USE_SIMULATOR = os.getenv("ORACLE_USE_SIMULATOR", "true").lower() == "true"

    # ========== AZURE OPENAI SETTINGS ==========
    AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
    AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4")
    AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

    # Feature flags
    USE_AI_ENGINE = True  # Azure OpenAI is now configured

    # ========== FILE PATHS ==========
    ORACLE_METADATA_PATH = "data/oracle_metadata.json"
    SQLSERVER_METADATA_PATH = "data/metadata.json"
    MAPPINGS_PATH = "data/mappings.json"
    DDL_OUTPUT_PATH = "data/migration_ddl.sql"
    REPORT_PATH = "data/migration_report.json"
