from locust import HttpUser, between, task


class PatientUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def consultation(self):
        r = self.client.post(
            "/api/v1/sessions",
            json={"patient_id": "load_user", "channel": "text"},
        )
        sid = r.json()["session_id"]
        self.client.post(
            f"/api/v1/sessions/{sid}/messages",
            json={
                "session_id": sid,
                "user_id": "load_user",
                "text": "I have had a headache for 3 days.",
            },
        )
