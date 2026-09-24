"""Deterministic schema compatibility scoring for the migration POC."""


class CompatibilityScorer:
    """Score source-schema migration readiness without relying on an LLM."""

    WEIGHTS = {
        "datatype_mapping": 40,
        "precision_scale": 20,
        "length": 10,
        "nullable": 10,
        "primary_keys": 10,
        "foreign_keys": 5,
        "indexes": 5,
    }

    def analyze(self, schema, datatype_analysis, constraints=None, indexes=None):
        """Return checks and a weighted 0-100 compatibility score.

        ``constraints`` uses Oracle constraint rows with ``constraint_type`` P or R.
        ``indexes`` uses Oracle index rows. Empty lists are valid and mean the source
        has no objects of that kind; ``None`` means metadata was not collected.
        """
        constraints_available = constraints is not None
        indexes_available = indexes is not None
        constraints = constraints or []
        indexes = indexes or []
        analysis_by_column = {
            (item.get("table", "").upper(), item.get("column", "").upper()): item
            for item in datatype_analysis
        }

        column_checks = []
        for column in schema:
            key = (
                str(column.get("table_name", "")).upper(),
                str(column.get("column_name", "")).upper(),
            )
            analysis = analysis_by_column.get(key, {})
            status = analysis.get("status", "Review Required")
            risk = analysis.get("risk", "Medium")
            compatible = status == "Compatible" and risk == "Low"
            column_checks.append({
                "table": key[0],
                "column": key[1],
                "datatype_mapping": self._result(compatible),
                "precision_scale": self._result(self._dimensions_present(column, "data_precision", "data_scale")),
                "length": self._result(self._length_present(column)),
                "nullable": self._result(column.get("nullable") is not None),
                "source_nullable": column.get("nullable"),
                "target_type": analysis.get("target_type"),
                "risk": risk,
            })

        primary_keys = [row for row in constraints if row.get("constraint_type") == "P"]
        foreign_keys = [row for row in constraints if row.get("constraint_type") == "R"]
        checks = {
            "datatype_mapping": self._aggregate(column_checks, "datatype_mapping"),
            "precision_scale": self._aggregate(column_checks, "precision_scale"),
            "length": self._aggregate(column_checks, "length"),
            "nullable": self._aggregate(column_checks, "nullable"),
            "primary_keys": self._metadata_result(constraints_available, primary_keys),
            "foreign_keys": self._metadata_result(constraints_available, foreign_keys),
            "indexes": self._metadata_result(indexes_available, indexes),
        }
        score = self._score(checks)

        return {
            "compatibility_score": score,
            "status": self._score_status(score),
            "checks": checks,
            "column_checks": column_checks,
            "primary_key_count": len(primary_keys),
            "foreign_key_count": len(foreign_keys),
            "index_count": len(indexes),
        }

    @staticmethod
    def _result(passed):
        return "Pass" if passed else "Review"

    @staticmethod
    def _dimensions_present(column, precision_key, scale_key):
        data_type = str(column.get("data_type", "")).upper()
        if not any(name in data_type for name in ("NUMBER", "DECIMAL", "NUMERIC", "FLOAT")):
            return True
        return column.get(precision_key) is not None and column.get(scale_key) is not None

    @staticmethod
    def _length_present(column):
        data_type = str(column.get("data_type", "")).upper()
        if not any(name in data_type for name in ("CHAR", "RAW", "BINARY")):
            return True
        return column.get("data_length") is not None

    @staticmethod
    def _aggregate(column_checks, field):
        if not column_checks:
            return "Not Available"
        return "Pass" if all(check[field] == "Pass" for check in column_checks) else "Review"

    @staticmethod
    def _metadata_result(available, rows):
        if not available:
            return "Not Available"
        return "Pass" if rows is not None else "Review"

    def _score(self, checks):
        applicable_weight = sum(
            weight for name, weight in self.WEIGHTS.items()
            if checks[name] != "Not Available"
        )
        if not applicable_weight:
            return 0
        passed_weight = sum(
            self.WEIGHTS[name] for name, result in checks.items()
            if result == "Pass"
        )
        return round(passed_weight * 100 / applicable_weight, 2)

    @staticmethod
    def _score_status(score):
        if score >= 90:
            return "Compatible"
        if score >= 70:
            return "Review"
        return "High Risk"