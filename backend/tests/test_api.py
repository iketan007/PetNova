"""API-level regression tests for authentication and private workspace endpoints."""
import os
import tempfile
import unittest

_test_dir = tempfile.TemporaryDirectory()
os.environ["PETNOVA_DB_PATH"] = os.path.join(_test_dir.name, "api-test.sqlite3")
os.environ["PETNOVA_AUTH_SECRET"] = "api-tests-only-secret-0123456789-abcdef"
os.environ["ALLOWED_ORIGINS"] = "http://testserver"

from fastapi.testclient import TestClient  # noqa: E402
from app import petnova_data  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


class WorkspaceAPITests(unittest.TestCase):
    def setUp(self):
        petnova_data.init_db()
        with petnova_data._connect() as db:
            db.execute("DELETE FROM reminders")
            db.execute("DELETE FROM health_records")
            db.execute("DELETE FROM pets")
            db.execute("DELETE FROM users")

    def register(self, email="parent@example.com", password="safe-test-password"):
        response = client.post("/auth/register", json={
            "name": "Pet Parent", "email": email, "password": password
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["token"]

    def auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_register_login_and_current_user(self):
        token = self.register()
        me = client.get("/auth/me", headers=self.auth(token))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["email"], "parent@example.com")

        login = client.post("/auth/login", json={
            "email": "PARENT@example.com", "password": "safe-test-password"
        })
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["user"]["email"], "parent@example.com")

    def test_duplicate_registration_and_invalid_login(self):
        self.register()
        duplicate = client.post("/auth/register", json={
            "name": "Another Parent", "email": "PARENT@example.com",
            "password": "safe-test-password"
        })
        self.assertEqual(duplicate.status_code, 409)
        bad_login = client.post("/auth/login", json={
            "email": "parent@example.com", "password": "wrong-password"
        })
        self.assertEqual(bad_login.status_code, 401)

    def test_workspace_rejects_missing_and_invalid_tokens(self):
        self.assertEqual(client.get("/pets").status_code, 401)
        self.assertEqual(client.get("/pets", headers=self.auth("invalid.token")).status_code, 401)

    def test_pet_crud_and_cross_account_isolation(self):
        owner = self.register()
        other = self.register("other@example.com")
        created = client.post("/pets", headers=self.auth(owner), json={
            "name": "Milo", "species": "Dog", "weight": 8.5
        })
        self.assertEqual(created.status_code, 201, created.text)
        pet_id = created.json()["pet"]["id"]

        self.assertEqual(client.get("/pets", headers=self.auth(other)).json()["pets"], [])
        self.assertEqual(client.patch(
            f"/pets/{pet_id}", headers=self.auth(other), json={"name": "Stolen"}
        ).status_code, 404)
        self.assertEqual(client.delete(
            f"/pets/{pet_id}", headers=self.auth(other)
        ).status_code, 404)

        updated = client.patch(
            f"/pets/{pet_id}", headers=self.auth(owner), json={"name": "Milo Jr"}
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["pet"]["name"], "Milo Jr")
        self.assertEqual(client.delete(
            f"/pets/{pet_id}", headers=self.auth(owner)
        ).status_code, 200)

    def test_health_records_and_reminders_are_user_scoped(self):
        owner = self.register()
        other = self.register("other@example.com")
        pet_response = client.post("/pets", headers=self.auth(owner), json={
            "name": "Milo", "species": "Dog"
        })
        pet_id = pet_response.json()["pet"]["id"]

        record = client.post("/health-records", headers=self.auth(owner), json={
            "pet_id": pet_id, "title": "Vaccination", "record_date": "2026-11-02"
        })
        self.assertEqual(record.status_code, 201, record.text)
        record_id = record.json()["record"]["id"]
        self.assertEqual(client.get(
            f"/health-records?pet_id={pet_id}", headers=self.auth(other)
        ).status_code, 404)
        self.assertEqual(client.delete(
            f"/health-records/{record_id}", headers=self.auth(other)
        ).status_code, 404)

        reminder = client.post("/reminders", headers=self.auth(owner), json={
            "pet_id": pet_id, "title": "Give medicine", "due_at": "2026-11-03T10:00:00"
        })
        self.assertEqual(reminder.status_code, 201, reminder.text)
        reminder_id = reminder.json()["reminder"]["id"]
        self.assertEqual(client.patch(
            f"/reminders/{reminder_id}", headers=self.auth(other), json={"completed": True}
        ).status_code, 404)
        self.assertEqual(client.patch(
            f"/reminders/{reminder_id}", headers=self.auth(owner), json={"completed": True}
        ).status_code, 200)

    def test_pet_input_validation(self):
        token = self.register()
        bad_species = client.post("/pets", headers=self.auth(token), json={
            "name": "Milo", "species": "Dragon"
        })
        self.assertEqual(bad_species.status_code, 422)
        bad_weight = client.post("/pets", headers=self.auth(token), json={
            "name": "Milo", "species": "Dog", "weight": -2
        })
        self.assertEqual(bad_weight.status_code, 422)


if __name__ == "__main__":
    unittest.main()
