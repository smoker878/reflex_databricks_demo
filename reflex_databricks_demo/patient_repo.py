from typing import Sequence

import reflex as rx
import sqlmodel

from .models import Patient


def list_patients() -> Sequence[Patient]:
    """Return all patients ordered by priority (ascending)."""
    with rx.session() as session:
        return session.exec(
            sqlmodel.select(Patient).order_by(Patient.priority)
        ).all()


def list_waiting_patients() -> Sequence[Patient]:
    """Return patients whose status is 'waiting', ordered by priority."""
    with rx.session() as session:
        return session.exec(
            sqlmodel.select(Patient)
            .where(Patient.status == "waiting")
            .order_by(Patient.priority)
        ).all()


def patient_count() -> int:
    """Return the total number of patients."""
    with rx.session() as session:
        return len(session.exec(sqlmodel.select(Patient)).all())


def seed_patients() -> int:
    """Insert demo patients if the table is empty. Idempotent.

    Returns the number of rows inserted.
    """
    with rx.session() as session:
        existing = session.exec(sqlmodel.select(Patient)).first()
        if existing is not None:
            return 0

        demo = [
            Patient(
                patient_id="P001",
                name="Amy",
                department="Internal Medicine",
                priority=3,
                status="waiting",
            ),
            Patient(
                patient_id="P002",
                name="Bob",
                department="Surgery",
                priority=1,
                status="waiting",
            ),
            Patient(
                patient_id="P003",
                name="Cindy",
                department="Pediatrics",
                priority=2,
                status="done",
            ),
        ]
        session.add_all(demo)
        session.commit()
        return len(demo)
