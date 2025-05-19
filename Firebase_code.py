# firebase_banking.py
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import uuid
import hashlib
import logging
from datetime import datetime, timezone, timedelta
import re
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BankingSystem:
    def __init__(self):
        if not firebase_admin._apps:
            cred_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        self.db = firestore.client()

    def validate_email(self, email):
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email)

    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

    def create_account(self, name, password, email):
        if not self.validate_email(email):
            raise ValueError("Invalid email format")

        hashed_pw = self.hash_password(password)

        # Check if email exists
        users = self.db.collection("accounts").where("email", "==", email).stream()
        if any(users):
            raise ValueError("Email already registered")

        account_no = str(uuid.uuid4())[:8].upper()
        self.db.collection("accounts").document(account_no).set({
            "name": name,
            "password": hashed_pw,
            "email": email,
            "balance": 0.0,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        return account_no
    
    def validate_login(self, account_no, password):
        hashed_pw = self.hash_password(password)
        doc = self.db.collection("accounts").document(account_no).get()
        if doc.exists and doc.to_dict()["password"] == hashed_pw:
            user = doc.to_dict()
            return account_no, user["name"], user["email"], user["balance"]
        return None

    def get_user_details(self, account_no):
        doc = self.db.collection("accounts").document(account_no).get()
        if doc.exists:
            data = doc.to_dict()
            return data["name"], data["email"], data["balance"], data["created_at"]
        return None

    def get_balance(self, account_no):
        doc = self.db.collection("accounts").document(account_no).get()
        if doc.exists:
            return doc.to_dict().get("balance", 0.0)
        return 0.0

    def record_transaction(self, account_no, txn_type, amount, category, recipient=None):
        try:
            account_ref = self.db.collection("accounts").document(account_no)
            account = account_ref.get().to_dict()
            balance = account.get("balance", 0.0)

            if txn_type == "withdraw" and amount > balance:
                return False

            new_balance = balance + amount if txn_type == "deposit" else balance - amount
            account_ref.update({"balance": new_balance})

            txn = {
                "account_no": account_no,
                "transaction_type": txn_type,
                "amount": amount,
                "category": category,
                "recipient_account": recipient,
                "timestamp": datetime.utcnow().isoformat()
            }

            self.db.collection("transactions").add(txn)
            return True
        except Exception as e:
            logger.error(f"Transaction failed: {str(e)}")
            return False

    def transfer_money(self, from_acc, to_acc, amount):
        try:
            sender = self.db.collection("accounts").document(from_acc).get()
            receiver = self.db.collection("accounts").document(to_acc).get()

            if not receiver.exists:
                return False, "Recipient account not found"
            sender_data = sender.to_dict()
            if sender_data["balance"] < amount:
                return False, "Insufficient funds"

            # Update balances
            self.db.collection("accounts").document(from_acc).update({
                "balance": sender_data["balance"] - amount
            })
            self.db.collection("accounts").document(to_acc).update({
                "balance": receiver.to_dict()["balance"] + amount
            })

            # Log transactions
            now = datetime.now(timezone.utc).isoformat()
            self.db.collection("transactions").add({
                "account_no": from_acc,
                "transaction_type": "transfer_out",
                "amount": amount,
                "category": "Transfer",
                "recipient_account": to_acc,
                "timestamp": now
            })
            self.db.collection("transactions").add({
                "account_no": to_acc,
                "transaction_type": "transfer_in",
                "amount": amount,
                "category": "Transfer",
                "recipient_account": from_acc,
                "       timestamp": now
            })

            return True, "Transfer successful"
        except Exception as e:
            return False, f"Transfer failed: {str(e)}"
        
    def apply_for_loan(self, account_no, amount, term_months, interest_rate):
        try:
            total_interest = (amount * interest_rate * term_months) / (12 * 100)
            total_amount = amount + total_interest
            monthly_payment = total_amount / term_months
            next_payment_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

            # Update balance
            acc_ref = self.db.collection("accounts").document(account_no)
            acc_data = acc_ref.get().to_dict()
            acc_ref.update({
                "balance": acc_data["balance"] + amount
            })

            # Record loan
            loan = {
                "account_no": account_no,
                "amount": amount,
                "interest_rate": interest_rate,
                "term_months": term_months,
                "monthly_payment": monthly_payment,
                "remaining_amount": total_amount,
                "status": "active",
                "start_date": datetime.now(timezone.utc).isoformat(),
                "next_payment_date": next_payment_date
            }
            self.db.collection("loans").add(loan)

            # Record transaction
            self.db.collection("transactions").add({
                "account_no": account_no,
                "transaction_type": "loan_disbursement",
                "amount": amount,
                "category": "Loan",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            return True, "Loan approved"
        except Exception as e:
            return False, f"Loan failed: {str(e)}"

    def get_active_loans(self, account_no):
        try:
            loans = self.db.collection("loans") \
                .where("account_no", "==", account_no) \
                .where("status", "==", "active") \
                .stream()
            return [loan.to_dict() | {"loan_id": loan.id} for loan in loans]
        except Exception as e:
            logger.error(f"Error fetching loans: {str(e)}")
            return []

    def make_loan_payment(self, loan_id, payment_amount):
        try:
            loan_ref = self.db.collection("loans").document(loan_id)
            loan = loan_ref.get().to_dict()
            if not loan or loan["status"] != "active":
                return False, "Loan not found or inactive"

            acc_ref = self.db.collection("accounts").document(loan["account_no"])
            acc = acc_ref.get().to_dict()

            if acc["balance"] < payment_amount:
                return False, "Insufficient funds"

            new_remaining = loan["remaining_amount"] - payment_amount
            new_status = "completed" if new_remaining <= 0 else "active"
            next_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

            # Update loan & account
            loan_ref.update({
                "remaining_amount": new_remaining,
                "next_payment_date": next_date,
                "status": new_status
            })
            acc_ref.update({
                "balance": acc["balance"] - payment_amount
            })

            # Log transaction
            self.db.collection("transactions").add({
                "account_no": loan["account_no"],
                "transaction_type": "loan_payment",
                "amount": payment_amount,
                "category": "Loan Payment",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            return True, "Payment successful"
        except Exception as e:
            return False, f"Payment failed: {str(e)}"

    def get_transaction_history(self, account_no):
        try:
            txns = self.db.collection("transactions") \
                .where("account_no", "==", account_no) \
                .order_by("timestamp", direction=firestore.Query.DESCENDING) \
                .stream()
            return [txn.to_dict() for txn in txns]
        except Exception as e:
            logger.error(f"Error fetching transactions: {str(e)}")
            return []

