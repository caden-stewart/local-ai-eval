#!/usr/bin/env python3
"""Generate the structured Alder & Finch documents and the question set.

The policy documents in docs/01-08 are written by hand. The staff directory,
client roster and invoice ledger are generated here from a fixed random seed,
along with questions whose answers are computed from the same data, so the
answer key can't drift from the documents. Re-running produces identical files.

    ./tests/smallbiz/make_data.py
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE / "docs"
SEED = 2027
N_CLIENTS = 500
N_INVOICES = 400

PARTNERS = ["Margaret Alder", "Thomas Finch", "Rosa Delgado"]
MANAGERS = ["Priya Shah", "Daniel Okoro", "Hannah Weiss", "Marco Bellini"]
STAFF = [
    ("Margaret Alder", "Managing partner", "Main"), ("Thomas Finch", "Partner", "Main"),
    ("Rosa Delgado", "Partner", "Main"), ("Kevin Park", "Operations Manager", "Main"),
    ("Priya Shah", "Tax manager", "Main"), ("Daniel Okoro", "Tax manager", "Main"),
    ("Hannah Weiss", "Advisory manager", "Main"), ("Marco Bellini", "Bookkeeping manager", "Harbor"),
    ("Aisha Rahman", "Senior accountant", "Main"), ("Ben Carter", "Senior accountant", "Main"),
    ("Chloe Nguyen", "Senior accountant", "Harbor"), ("Diego Alvarez", "Senior accountant", "Main"),
    ("Emma Lindqvist", "Staff accountant", "Main"), ("Farid Haddad", "Staff accountant", "Harbor"),
    ("Grace Kim", "Staff accountant", "Main"), ("Henry Osei", "Staff accountant", "Harbor"),
    ("Isabel Moreno", "Staff accountant", "Main"), ("Jamal Wright", "Payroll specialist", "Harbor"),
    ("Keiko Tanaka", "Payroll specialist", "Harbor"), ("Liam O'Brien", "Bookkeeper", "Harbor"),
    ("Maya Patel", "Bookkeeper", "Harbor"), ("Noah Fischer", "Administrative assistant", "Main"),
    ("Olivia Brooks", "Receptionist", "Main"), ("Pedro Santos", "IT support contractor", "Main"),
]

PLACES = ["Harbor", "Summit", "Cedar", "Blue Ridge", "Oakmont", "Silverline", "Redwood", "Lakeside", "Pinecrest",
          "Northgate", "Sunset", "Copper", "Meadow", "Riverbend", "Stonebridge", "Westfield", "Brightwater",
          "Golden Gate", "Maple", "Coastal", "Highland", "Ironwood", "Juniper", "Kingsley", "Larkin", "Mission",
          "Orchard", "Pacific", "Quarry", "Rosewood"]
TRADES = ["Landscaping", "Dental", "Bakery", "Auto Repair", "Plumbing", "Veterinary", "Physical Therapy",
          "Roofing", "Coffee Roasters", "Electric", "Fitness", "Florist", "HVAC", "Cleaning", "Catering",
          "Printing", "Pet Grooming", "Tutoring", "Construction", "Design Studio"]
FIRST = ["Alex", "Blake", "Casey", "Dana", "Elliot", "Frankie", "Gabriel", "Harper", "Isaac", "Jordan", "Kendall",
         "Logan", "Morgan", "Nico", "Owen", "Parker", "Quinn", "Riley", "Sasha", "Taylor", "Uma", "Victor",
         "Wren", "Yusuf", "Zoe"]
LAST = ["Abbott", "Barrera", "Chen", "Dawson", "Everett", "Flores", "Garner", "Holloway", "Ingram", "Jensen",
        "Kowalski", "Lopez", "Mercer", "Nakamura", "Ortega", "Pruitt", "Quintana", "Ramsey", "Sutton", "Thornton",
        "Underwood", "Vasquez", "Whitfield", "Yates", "Zamora"]
BUSINESS_TYPES = ["S-Corp", "Partnership", "C-Corp", "Nonprofit"]
STATUSES = ["active"] * 7 + ["onboarding", "extension filed", "paused"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def date_anchors(d: date) -> list[str]:
    return [d.isoformat(), f"{MONTHS[d.month - 1]} {d.day}", f"{MONTHS[d.month - 1][:3]} {d.day}", f"{d.month}/{d.day}"]


def build() -> tuple[list[dict], list[dict]]:
    rng = random.Random(SEED)

    clients = []
    used: set[str] = set()
    while len(clients) < N_CLIENTS:
        entity = rng.choice(["Individual"] * 4 + BUSINESS_TYPES)
        if entity == "Individual":
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        else:
            name = f"{rng.choice(PLACES)} {rng.choice(TRADES)}"
        if name in used or name == "Brightwater Landscaping":  # that name belongs to the handwritten memo
            continue
        used.add(name)
        clients.append({
            "id": f"C-{1001 + len(clients)}",
            "name": name,
            "entity": entity,
            "partner": rng.choice(PARTNERS),
            "manager": rng.choice(MANAGERS),
            "fee": rng.randrange(900, 24000, 50),
            "deadline": date(2027, 1, 15) + timedelta(days=rng.randrange(0, 300)),
            "status": rng.choice(STATUSES),
        })

    invoices = []
    for i in range(N_INVOICES):
        client = rng.choice(clients)
        issued = date(2026, 9, 1) + timedelta(days=rng.randrange(0, 180))
        amount = rng.randrange(150, 6000, 25)
        state = rng.choice(["paid"] * 6 + ["unpaid", "unpaid", "partially paid"])
        paid = amount if state == "paid" else (0 if state == "unpaid" else rng.randrange(50, amount, 25))
        invoices.append({"id": f"INV-{24001 + i}", "client_id": client["id"], "issued": issued,
                         "amount": amount, "status": state, "paid": paid})
    return clients, invoices


def write_docs(clients: list[dict], invoices: list[dict]) -> None:
    staff_lines = ["# Staff directory", "", "| Name | Title | Office |", "| --- | --- | --- |"]
    staff_lines += [f"| {n} | {t} | {o} |" for n, t, o in STAFF]
    (DOCS / "09-staff-directory.md").write_text("\n".join(staff_lines) + "\n", encoding="utf-8")

    roster = ["# Client roster", "", "Fees are fixed annual fees. Deadline is the next filing or extension deadline.", "",
              "| Client ID | Client | Entity | Partner | Manager | Annual fee | Next deadline | Status |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    roster += [f"| {c['id']} | {c['name']} | {c['entity']} | {c['partner']} | {c['manager']} | ${c['fee']:,} | "
               f"{c['deadline'].isoformat()} | {c['status']} |" for c in clients]
    (DOCS / "10-client-roster.md").write_text("\n".join(roster) + "\n", encoding="utf-8")

    ledger = ["# Invoice ledger", "", "| Invoice | Client ID | Issued | Amount | Status | Amount paid |",
              "| --- | --- | --- | --- | --- | --- |"]
    ledger += [f"| {v['id']} | {v['client_id']} | {v['issued'].isoformat()} | ${v['amount']:,} | {v['status']} | "
               f"${v['paid']:,} |" for v in invoices]
    (DOCS / "11-invoice-ledger.md").write_text("\n".join(ledger) + "\n", encoding="utf-8")


def build_questions(clients: list[dict], invoices: list[dict]) -> list[dict]:
    rng = random.Random(SEED + 1)
    by_id = {c["id"]: c for c in clients}
    q: list[dict] = []

    def add(question: str, groups: list[list[str]] | None) -> None:
        q.append({"id": f"q{len(q) + 1:02d}", "question": question,
                  "answerable": groups is not None, "any_of_groups": groups or []})

    # Handwritten policy questions.
    add("How long does the firm keep payroll records?", [["4 year", "four year"]])
    add("What late fee applies to unpaid invoices, and when does it start?", [["1.5"], ["30 days", "thirty days"]])
    add("When is the PTO blackout period during tax season?",
        [["march 1", "mar 1", "3/1"], ["april 15", "apr 15", "4/15"]])
    add("A laptop was stolen. Within how long must it be reported, and to whom?",
        [["1 hour", "one hour"], ["kevin park"]])
    add("What's the last day to accept new individual tax clients this season?", [["march 20", "mar 20", "3/20"]])
    add("What is the hourly rate for a senior?", [["185"]])
    add("For the Brightwater Landscaping S-Corp election matter, who is the assigned partner and what is the estimated fee?",
        [["finch"], ["1800"]])
    add("What surcharge applies when a client pays by card?", [["3%", "3 percent", "three percent"]])

    # Generated lookups, answers computed from the roster and ledger.
    c = rng.choice(clients)
    add(f"What is the annual fee for {c['name']} ({c['id']})?", [[str(c["fee"])]])

    c = rng.choice([x for x in clients if x["entity"] != "Individual"])
    add(f"Which partner is assigned to {c['name']}?", [[c["partner"].split()[-1]]])

    c = rng.choice(clients)
    add(f"Who is the manager for client {c['id']}, and what is that client's next deadline?",
        [[c["manager"].split()[-1]], date_anchors(c["deadline"])])

    v = rng.choice([x for x in invoices if x["status"] == "partially paid"])
    add(f"How much is still owed on invoice {v['id']}?", [[str(v["amount"] - v["paid"])]])

    v = rng.choice([x for x in invoices if x["status"] == "unpaid"])
    owner = by_id[v["client_id"]]
    add(f"Which client is invoice {v['id']} for, and what's its amount?", [[owner["name"].lower()], [str(v["amount"])]])

    count = sum(1 for x in clients if x["partner"] == "Rosa Delgado" and x["entity"] == "S-Corp" and x["status"] == "active")
    add("How many active S-Corp clients does Rosa Delgado handle?", [[str(count)]])

    manager_counts = {m: sum(1 for x in clients if x["manager"] == m and x["status"] == "paused") for m in MANAGERS}
    top = max(manager_counts, key=manager_counts.get)
    add("Which manager has the most clients with a paused status, and how many?",
        [[top.split()[-1]], [str(manager_counts[top])]])

    # Unanswerable: nothing in the documents covers these.
    add("What is the firm's 401(k) employer match?", None)
    add("What is the parking arrangement for staff at the Harbor Street office?", None)
    add("What is Kevin Park's phone number?", None)
    add("What year was Alder & Finch founded?", None)
    add("Which shredding company does the firm use?", None)
    return q


def main() -> None:
    clients, invoices = build()
    write_docs(clients, invoices)
    questions = build_questions(clients, invoices)
    (HERE / "questions.json").write_text(json.dumps(questions, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(clients)} clients, {len(invoices)} invoices, {len(questions)} questions.")


if __name__ == "__main__":
    main()
