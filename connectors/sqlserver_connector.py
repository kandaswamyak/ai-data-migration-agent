import pyodbc


class SQLServerConnector:

    def __init__(self, server, database):
        self.server = server
        self.database = database

    def connect(self):

        connection_string = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={self.server};"
            f"DATABASE={self.database};"
            "Trusted_Connection=yes;"
            "Encrypt=yes;"
            "TrustServerCertificate=yes;"
        )

        conn = pyodbc.connect(connection_string)

        return conn
