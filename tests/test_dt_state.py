import unittest

from Modules.Tools.dt_state import DTStateManager


class DTStateManagerTests(unittest.TestCase):
    def test_default_state_is_available(self):
        manager = DTStateManager()

        result = manager.get_DT_state(dt_name="es_dt")

        self.assertEqual(result["dt_name"], "es_dt")
        self.assertEqual(result["status"], "deactivate")

    def test_legacy_argument_aliases_still_work(self):
        manager = DTStateManager()

        result = manager.set_DT_state(DT="es_dt", Setting="activate")

        self.assertEqual(result["dt_name"], "es_dt")
        self.assertEqual(result["status"], "activate")


if __name__ == "__main__":
    unittest.main()
