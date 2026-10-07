import json


class CompatibilityAgent:

    def __init__(self, target="Azure SQL"):
        self.target = target

    def load_oracle_schema(self, file_path="data/oracle_metadata.json"):

        with open(file_path, "r") as file:
            return json.load(file)

    def analyze_column(self, column):

        source_type = column["DATA_TYPE"].upper()

        precision = column.get("DATA_PRECISION")
        scale = column.get("DATA_SCALE")

        # Oracle NUMBER
        if source_type == "NUMBER":

            if precision is not None and scale == 0 and precision <= 10:
                return {
                    "target_type": "INT",
                    "status": "Compatible",
                    "risk": "Low",
                    "confidence": 0.98,
                    "recommendation": "NUMBER with precision <=10 and scale 0 maps safely to INT."
                }

            if precision is not None and scale == 0 and precision <= 19:
                return {
                    "target_type": "BIGINT",
                    "status": "Compatible",
                    "risk": "Low",
                    "confidence": 0.97,
                    "recommendation": "NUMBER with precision <=19 and scale 0 maps to BIGINT."
                }

            if precision is not None and precision == 1 and scale == 0:
                return {
                    "target_type": "BIT",
                    "status": "Compatible",
                    "risk": "Low",
                    "confidence": 0.95,
                    "recommendation": "NUMBER(1,0) represents boolean. Maps to BIT."
                }

            if precision is not None:
                target_type = f"DECIMAL({precision},{scale or 0})"

                return {
                    "target_type": target_type,
                    "status": "Compatible",
                    "risk": "Low",
                    "confidence": 0.95,
                    "recommendation": f"Map Oracle NUMBER({precision},{scale or 0}) to {target_type}."
                }

            return {
                "target_type": "DECIMAL(38,10)",
                "status": "Warning",
                "risk": "Medium",
                "confidence": 0.75,
                "recommendation": "Oracle NUMBER without explicit precision. Review target precision requirement."
            }

        # Oracle VARCHAR2
        if source_type == "VARCHAR2":

            length = column.get("DATA_LENGTH")

            return {
                "target_type": f"NVARCHAR({length})",
                "status": "Warning",
                "risk": "Low",
                "confidence": 0.92,
                "recommendation": "Convert VARCHAR2 to NVARCHAR. Verify Unicode and character length requirements."
            }

        # Oracle DATE
        if source_type == "DATE":

            return {
                "target_type": "DATETIME2",
                "status": "Warning",
                "risk": "Medium",
                "confidence": 0.90,
                "recommendation": "Oracle DATE stores date+time. DATETIME2 preserves both. Verify time precision requirements."
            }

        # Oracle CLOB
        if source_type == "CLOB":

            return {
                "target_type": "NVARCHAR(MAX)",
                "status": "Warning",
                "risk": "Medium",
                "confidence": 0.85,
                "recommendation": "CLOB maps to NVARCHAR(MAX). Verify max data size does not exceed Azure SQL limits (2GB)."
            }

        # Oracle BLOB
        if source_type == "BLOB":

            return {
                "target_type": "VARBINARY(MAX)",
                "status": "Warning",
                "risk": "Medium",
                "confidence": 0.85,
                "recommendation": "BLOB maps to VARBINARY(MAX). Verify binary data size requirements."
            }

        # Oracle TIMESTAMP
        if source_type in ("TIMESTAMP", "TIMESTAMP(6)", "TIMESTAMP(9)"):

            return {
                "target_type": "DATETIME2(7)",
                "status": "Warning",
                "risk": "Low",
                "confidence": 0.92,
                "recommendation": "Oracle TIMESTAMP maps to DATETIME2. Azure SQL supports up to 7 fractional digits."
            }

        # Unknown datatype
        return {
            "target_type": "UNKNOWN",
            "status": "Error",
            "risk": "High",
            "confidence": 0.0,
            "recommendation": f"No mapping rule for Oracle datatype '{source_type}'. Manual review required."
        }

    def analyze_schema(self, schema):

        results = []

        for table_name, columns in schema.items():

            for column in columns:

                analysis = self.analyze_column(column)

                precision = column.get("DATA_PRECISION")
                scale = column.get("DATA_SCALE")

                if precision is not None and scale is not None:
                    source_display = f"{column['DATA_TYPE']}({precision},{scale})"
                elif precision is not None:
                    source_display = f"{column['DATA_TYPE']}({precision})"
                else:
                    source_display = column["DATA_TYPE"]

                result = {
                    "table": table_name,
                    "column": column["COLUMN_NAME"],
                    "source_type": source_display,
                    "nullable": column.get("NULLABLE", "Y"),
                    "target_type": analysis["target_type"],
                    "status": analysis["status"],
                    "risk": analysis["risk"],
                    "confidence": analysis["confidence"],
                    "recommendation": analysis["recommendation"]
                }

                results.append(result)

        return results
