"""Focused tests for PetNova account/session and user-scoped data helpers."""
import os
import tempfile
import unittest

_test_dir = tempfile.TemporaryDirectory()
os.environ["PETNOVA_DB_PATH"] = os.path.join(_test_dir.name, "test.sqlite3")
os.environ["PETNOVA_AUTH_SECRET"] = "test-only-secret-for-petnova-unit-tests-123456789"

from app import petnova_data as data  # noqa: E402


class PetNovaDataTests(unittest.TestCase):
    def setUp(self):
        with data._connect() as db:
            db.execute("DELETE FROM reminders")
            db.execute("DELETE FROM health_records")
            db.execute("DELETE FROM pets")
            db.execute("DELETE FROM users")

    def test_passwords_are_hashed_and_login_verifies(self):
        user = data.register_user("Test Parent", "parent@example.com", "safe-test-password")
        self.assertNotIn("password_hash", user)
        self.assertIsNotNone(data.authenticate_user("PARENT@example.com", "safe-test-password"))
        self.assertIsNone(data.authenticate_user("parent@example.com", "wrong-password"))

    def test_session_token_expires_and_is_signed(self):
        user = data.register_user("Test Parent", "parent@example.com", "safe-test-password")
        token = data.create_token(user["id"])
        self.assertEqual(data.verify_token(token), user["id"])
        self.assertIsNone(data.verify_token(token + "tampered"))

    def test_pet_access_is_scoped_to_owning_user(self):
        owner = data.register_user("Owner", "owner@example.com", "safe-test-password")
        other = data.register_user("Other", "other@example.com", "safe-test-password")
        pet = data.create_pet(owner["id"], {"name": "Milo", "species": "Dog"})
        self.assertEqual(data.get_pet(owner["id"], pet["id"])["name"], "Milo")
        self.assertIsNone(data.get_pet(other["id"], pet["id"]))
        self.assertFalse(data.delete_pet(other["id"], pet["id"]))
        self.assertTrue(data.delete_pet(owner["id"], pet["id"]))


if __name__ == "__main__":
    unittest.main()
