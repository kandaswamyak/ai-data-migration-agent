import unittest

from agents.compatibility_scorer import CompatibilityScorer


class CompatibilityScorerTests(unittest.TestCase):

    def test_scores_all_supported_checks(self):
        schema = [
            {
                "table_name": "ORDERS",
                "column_name": "ORDER_ID",
                "data_type": "NUMBER(10,0)",
                "data_precision": 10,
                "data_scale": 0,
                "data_length": 22,
                "nullable": "N",
            },
            {
                "table_name": "ORDERS",
                "column_name": "ORDER_NAME",
                "data_type": "VARCHAR2(100)",
                "data_precision": None,
                "data_scale": None,
                "data_length": 100,
                "nullable": "Y",
            },
        ]
        analysis = [
            {"table": "ORDERS", "column": "ORDER_ID", "target_type": "INT", "status": "Compatible", "risk": "Low"},
            {"table": "ORDERS", "column": "ORDER_NAME", "target_type": "NVARCHAR(100)", "status": "Compatible", "risk": "Low"},
        ]
        constraints = [
            {"constraint_name": "PK_ORDERS", "constraint_type": "P", "table_name": "ORDERS", "column_name": "ORDER_ID"},
            {"constraint_name": "FK_ORDERS_CUSTOMERS", "constraint_type": "R", "table_name": "ORDERS", "column_name": "CUSTOMER_ID"},
        ]
        indexes = [{"index_name": "IX_ORDERS_NAME", "table_name": "ORDERS", "column_name": "ORDER_NAME"}]

        result = CompatibilityScorer().analyze(schema, analysis, constraints, indexes)

        self.assertEqual(result["compatibility_score"], 100)
        self.assertEqual(result["status"], "Compatible")
        self.assertTrue(all(value == "Pass" for value in result["checks"].values()))
        self.assertEqual(result["primary_key_count"], 1)
        self.assertEqual(result["foreign_key_count"], 1)
        self.assertEqual(result["index_count"], 1)


if __name__ == "__main__":
    unittest.main()