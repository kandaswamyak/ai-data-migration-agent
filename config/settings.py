from dotenv import load_dotenv
import os

load_dotenv()

SQL_SERVER = os.getenv("SQL_SERVER")
SQL_DATABASE = os.getenv("SQL_DATABASE")
SQL_DRIVER = os.getenv("SQL_DRIVER")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
