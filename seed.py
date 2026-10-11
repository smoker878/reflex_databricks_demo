"""Seed the local SQLite database with demo data.

Usage:
    uv run python seed.py

Creates:
    - demo patients (for the /patients page)
    - two demo users (alice / bob, password: password123)
    - a short sample conversation between them

Idempotent: running it again changes nothing.
"""

import reflex as rx
import sqlmodel
from reflex_local_auth import LocalUser

from reflex_databricks_demo import chat_repo
from reflex_databricks_demo.models import Patient, conversation_key
from reflex_databricks_demo.patient_repo import seed_patients

DEMO_USERS = [
    ("alice", "password123"),
    ("bob", "password123"),
]


def seed_users() -> int:
    inserted = 0
    with rx.session() as session:
        for username, password in DEMO_USERS:
            existing = session.exec(
                sqlmodel.select(LocalUser).where(LocalUser.username == username)
            ).one_or_none()
            if existing is not None:
                continue
            user = LocalUser(  # type: ignore[call-arg]
                username=username,
                password_hash=LocalUser.hash_password(password),
                enabled=True,
            )
            session.add(user)
            inserted += 1
        session.commit()
    return inserted


def seed_conversation() -> int:
    with rx.session() as session:
        alice = session.exec(
            sqlmodel.select(LocalUser).where(LocalUser.username == "alice")
        ).one_or_none()
        bob = session.exec(
            sqlmodel.select(LocalUser).where(LocalUser.username == "bob")
        ).one_or_none()
    if alice is None or bob is None or alice.id is None or bob.id is None:
        return 0

    key = conversation_key(alice.id, bob.id)
    if chat_repo.list_messages(key, limit=1):
        return 0

    chat_repo.add_message(alice.id, alice.username, bob.id, "嗨 Bob，我是 Alice！")
    chat_repo.add_message(bob.id, bob.username, alice.id, "哈囉 Alice，一起聊天吧！")
    return 2


def main() -> None:
    Patient.create_all()

    patients = seed_patients()
    users = seed_users()
    messages = seed_conversation()

    print(f"patients inserted: {patients}")
    print(f"users inserted: {users}")
    print(f"messages inserted: {messages}")
    if users or messages or patients:
        print("Run the app and log in as alice / bob (password: password123).")
    else:
        print("Database already seeded; nothing to do.")


if __name__ == "__main__":
    main()
