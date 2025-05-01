import sqlite3
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import uuid
import hashlib
from datetime import datetime, timedelta
import os
import logging
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BankingSystem:
    def __init__(self):
        self.db_name = "banking.db"
        # Remove existing database file if it exists
        if os.path.exists(self.db_name):
            os.remove(self.db_name)
        self.conn = sqlite3.connect(self.db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def validate_email(self, email):
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(email_pattern, email) is not None

    def create_tables(self):
        # Accounts table
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            account_no TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            password TEXT NOT NULL,
            balance REAL NOT NULL DEFAULT 0.0,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')

        # Transactions table with recipient_account column
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_no TEXT NOT NULL,
            transaction_type TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT,
            recipient_account TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_no) REFERENCES accounts(account_no),
            FOREIGN KEY (recipient_account) REFERENCES accounts(account_no)
        );
        ''')

        # Loans table
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS loans (
            loan_id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_no TEXT NOT NULL,
            amount REAL NOT NULL,
            interest_rate REAL NOT NULL,
            term_months INTEGER NOT NULL,
            monthly_payment REAL NOT NULL,
            remaining_amount REAL NOT NULL,
            status TEXT NOT NULL,
            start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            next_payment_date TIMESTAMP,
            FOREIGN KEY (account_no) REFERENCES accounts(account_no)
        );
        ''')

        self.conn.commit()

    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

    def create_account(self, name, password, email):
        try:
            if not self.validate_email(email):
                raise ValueError("Invalid email format")

            account_no = str(uuid.uuid4())[:8].upper()
            hashed_password = self.hash_password(password)

            self.cursor.execute("""
                INSERT INTO accounts (account_no, name, password, email)
                VALUES (?, ?, ?, ?);
            """, (account_no, name, hashed_password, email))

            self.conn.commit()
            return account_no
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: accounts.email" in str(e):
                raise ValueError("Email already registered")
            raise e
        except Exception as e:
            raise ValueError(f"Error creating account: {str(e)}")

    def validate_login(self, account_no, password):
        try:
            hashed_password = self.hash_password(password)
            self.cursor.execute("""
                SELECT account_no, name, email, balance
                FROM accounts
                WHERE account_no = ? AND password = ?;
            """, (account_no, hashed_password))
            return self.cursor.fetchone()
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return None

    def get_user_details(self, account_no):
        try:
            self.cursor.execute("""
                SELECT name, email, balance, created_at
                FROM accounts
                WHERE account_no = ?;
            """, (account_no,))
            return self.cursor.fetchone()
        except Exception as e:
            logger.error(f"Error fetching user details: {str(e)}")
            return None

    def get_balance(self, account_no):
        try:
            self.cursor.execute("SELECT balance FROM accounts WHERE account_no = ?;", (account_no,))
            result = self.cursor.fetchone()
            return result[0] if result else 0.0
        except Exception as e:
            logger.error(f"Error fetching balance: {str(e)}")
            return 0.0

    def record_transaction(self, account_no, transaction_type, amount, category, recipient_account=None):
        try:
            self.cursor.execute("BEGIN TRANSACTION")

            # Check balance for withdrawals
            if transaction_type == "withdraw":
                current_balance = self.get_balance(account_no)
                if amount > current_balance:
                    self.cursor.execute("ROLLBACK")
                    return False

            # Insert transaction record
            self.cursor.execute("""
                INSERT INTO transactions (account_no, transaction_type, amount, category, recipient_account)
                VALUES (?, ?, ?, ?, ?);
            """, (account_no, transaction_type, amount, category, recipient_account))

            # Update account balance
            if transaction_type == "deposit":
                self.cursor.execute("""
                    UPDATE accounts 
                    SET balance = balance + ? 
                    WHERE account_no = ?;
                """, (amount, account_no))
            elif transaction_type == "withdraw":
                self.cursor.execute("""
                    UPDATE accounts 
                    SET balance = balance - ? 
                    WHERE account_no = ?;
                """, (amount, account_no))

            self.cursor.execute("COMMIT")
            return True
        except Exception as e:
            self.cursor.execute("ROLLBACK")
            logger.error(f"Transaction error: {str(e)}")
            return False

    def transfer_money(self, from_account, to_account, amount):
        try:
            # Verify recipient account exists
            self.cursor.execute("SELECT account_no FROM accounts WHERE account_no = ?", (to_account,))
            if not self.cursor.fetchone():
                return False, "Recipient account not found"

            # Check sender's balance
            sender_balance = self.get_balance(from_account)
            if amount > sender_balance:
                return False, "Insufficient funds"

            self.cursor.execute("BEGIN TRANSACTION")

            # Deduct from sender
            self.cursor.execute("""
                UPDATE accounts 
                SET balance = balance - ? 
                WHERE account_no = ?;
            """, (amount, from_account))

            # Add to recipient
            self.cursor.execute("""
                UPDATE accounts 
                SET balance = balance + ? 
                WHERE account_no = ?;
            """, (amount, to_account))

            # Record transfer transactions
            self.cursor.execute("""
                INSERT INTO transactions (account_no, transaction_type, amount, category, recipient_account)
                VALUES (?, 'transfer_out', ?, 'Transfer', ?);
            """, (from_account, amount, to_account))

            self.cursor.execute("""
                INSERT INTO transactions (account_no, transaction_type, amount, category, recipient_account)
                VALUES (?, 'transfer_in', ?, 'Transfer', ?);
            """, (to_account, amount, from_account))

            self.cursor.execute("COMMIT")
            return True, "Transfer successful"

        except Exception as e:
            self.cursor.execute("ROLLBACK")
            logger.error(f"Transfer error: {str(e)}")
            return False, f"Transfer failed: {str(e)}"

    def apply_for_loan(self, account_no, amount, term_months, interest_rate):
        try:
            # Calculate monthly payment using simple interest
            total_interest = (amount * interest_rate * term_months) / (12 * 100)
            total_amount = amount + total_interest
            monthly_payment = total_amount / term_months

            # Set next payment date
            next_payment_date = datetime.now() + timedelta(days=30)

            self.cursor.execute("""
                INSERT INTO loans (
                    account_no, amount, interest_rate, term_months, 
                    monthly_payment, remaining_amount, status, next_payment_date
                )
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?);
            """, (account_no, amount, interest_rate, term_months, 
                  monthly_payment, total_amount, next_payment_date))

            # Add loan amount to account balance
            self.cursor.execute("""
                UPDATE accounts 
                SET balance = balance + ? 
                WHERE account_no = ?;
            """, (amount, account_no))

            # Record loan disbursement as a transaction
            self.cursor.execute("""
                INSERT INTO transactions (account_no, transaction_type, amount, category)
                VALUES (?, 'loan_disbursement', ?, 'Loan');
            """, (account_no, amount))

            self.conn.commit()
            return True, "Loan approved"

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Loan application error: {str(e)}")
            return False, f"Loan application failed: {str(e)}"

    def get_active_loans(self, account_no):
        try:
            self.cursor.execute("""
                SELECT loan_id, amount, interest_rate, term_months, 
                       monthly_payment, remaining_amount, start_date, 
                       next_payment_date
                FROM loans
                WHERE account_no = ? AND status = 'active'
                ORDER BY start_date DESC;
            """, (account_no,))
            return self.cursor.fetchall()
        except Exception as e:
            logger.error(f"Error fetching loans: {str(e)}")
            return []

    def make_loan_payment(self, loan_id, payment_amount):
        try:
            self.cursor.execute("BEGIN TRANSACTION")

            # Get loan details
            self.cursor.execute("""
                SELECT account_no, remaining_amount, monthly_payment
                FROM loans
                WHERE loan_id = ? AND status = 'active';
            """, (loan_id,))
            loan_data = self.cursor.fetchone()

            if not loan_data:
                self.cursor.execute("ROLLBACK")
                return False, "Loan not found or inactive"

            account_no, remaining_amount, monthly_payment = loan_data

            # Check if account has sufficient balance
            balance = self.get_balance(account_no)
            if balance < payment_amount:
                self.cursor.execute("ROLLBACK")
                return False, "Insufficient funds"

            # Update loan remaining amount
            new_remaining = remaining_amount - payment_amount
            next_payment_date = datetime.now() + timedelta(days=30)

            self.cursor.execute("""
                UPDATE loans
                SET remaining_amount = ?,
                    next_payment_date = ?,
                    status = CASE 
                        WHEN remaining_amount - ? <= 0 THEN 'completed'
                        ELSE 'active'
                    END
                WHERE loan_id = ?;
            """, (new_remaining, next_payment_date, payment_amount, loan_id))

            # Deduct payment from account balance
            self.cursor.execute("""
                UPDATE accounts
                SET balance = balance - ?
                WHERE account_no = ?;
            """, (payment_amount, account_no))

            # Record payment transaction
            self.cursor.execute("""
                INSERT INTO transactions (account_no, transaction_type, amount, category)
                VALUES (?, 'loan_payment', ?, 'Loan Payment');
            """, (account_no, payment_amount))

            self.cursor.execute("COMMIT")
            return True, "Payment successful"

        except Exception as e:
            self.cursor.execute("ROLLBACK")
            logger.error(f"Loan payment error: {str(e)}")
            return False, f"Payment failed: {str(e)}"

    def get_transaction_history(self, account_no):
        try:
            self.cursor.execute("""
                SELECT transaction_type, amount, timestamp, category,
                       recipient_account
                FROM transactions
                WHERE account_no = ?
                ORDER BY timestamp DESC;
            """, (account_no,))
            return self.cursor.fetchall()
        except Exception as e:
            logger.error(f"Error fetching transactions: {str(e)}")
            return []

def main():
    st.set_page_config(page_title="Banking System", layout="wide")

    if 'banking_system' not in st.session_state:
        st.session_state.banking_system = BankingSystem()

    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    with st.sidebar:
        if not st.session_state.logged_in:
            st.title("Banking System")
            login_choice = st.radio("Choose action", ["Login", "Create Account"])

            if login_choice == "Create Account":
                with st.form("create_account_form"):
                    st.subheader("Create New Account")
                    name = st.text_input("Full Name")
                    email = st.text_input("Email Address")
                    password = st.text_input("Password", type="password")
                    confirm_password = st.text_input("Confirm Password", type="password")
                    submit = st.form_submit_button("Create Account")

                    if submit:
                        if not all([name, email, password, confirm_password]):
                            st.error("Please fill in all fields")
                        elif password != confirm_password:
                            st.error("Passwords do not match")
                        elif len(password) < 6:
                            st.error("Password must be at least 6 characters long")
                        else:
                            try:
                                account_no = st.session_state.banking_system.create_account(
                                    name, password, email
                                )
                                st.success(f"""Account created successfully!
                                    Your account number is: {account_no}
                                    Please save this number for login.""")
                            except ValueError as e:
                                st.error(str(e))

            else:
                with st.form("login_form"):
                    st.subheader("Login")
                    account_no = st.text_input("Account Number").strip().upper()
                    password = st.text_input("Password", type="password")
                    submit = st.form_submit_button("Login")

                    if submit:
                        if not account_no or not password:
                            st.error("Please fill in all fields")
                        else:
                            user = st.session_state.banking_system.validate_login(
                                account_no, password
                            )
                            if user:
                                st.session_state.logged_in = True
                                st.session_state.account_no = account_no
                                st.session_state.user_name = user[1]
                                st.rerun()
                            else:
                                st.error("Invalid account number or password")

        else:
            st.button("Logout", on_click=lambda: setattr(st.session_state, 'logged_in', False))

    if st.session_state.logged_in:
        user_details = st.session_state.banking_system.get_user_details(st.session_state.account_no)

        if user_details:
            name, email, balance, created_at = user_details

            st.title(f"Welcome, {name}!")

            # Key metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Current Balance", f"₹{balance:.2f}")
            with col2:
                st.metric("Account Number", st.session_state.account_no)
            with col3:
                st.metric("Member Since", created_at.split()[0])

            # Transaction section with tabs
            st.subheader("Banking Services")
            tabs = st.tabs([
                "Deposit/Withdraw", 
                "Transfer Money", 
                "Loans", 
                "Transaction History"
            ])

            # Deposit/Withdraw tab
            with tabs[0]:
                col1, col2 = st.columns(2)

                # Deposit form
                with col1:
                    with st.form("deposit_form"):
                        st.write("Deposit Money")
                        deposit_amount = st.number_input(
                            "Amount (₹)", 
                            min_value=0.01, 
                            step=0.01,
                            key="deposit_amount"
                        )
                        deposit_category = st.selectbox(
                            "Category",
                            ["Salary", "Investment", "Transfer", "Other"],
                            key="deposit_category"
                        )
                        deposit_submit = st.form_submit_button("Deposit")

                        if deposit_submit:
                            if st.session_state.banking_system.record_transaction(
                                st.session_state.account_no,
                                "deposit",
                                deposit_amount,
                                deposit_category
                            ):
                                st.success(f"Successfully deposited ₹{deposit_amount:.2f}")
                                st.rerun()
                            else:
                                st.error("Failed to process deposit")

                # Withdraw form
                with col2:
                    with st.form("withdraw_form"):
                        st.write("Withdraw Money")
                        withdraw_amount = st.number_input(
                            "Amount (₹)", 
                            min_value=0.01, 
                            step=0.01,
                            key="withdraw_amount"
                        )
                        withdraw_category = st.selectbox(
                            "Category",
                            ["Food", "Transport", "Bills", "Shopping", "Entertainment", "Other"],
                            key="withdraw_category"
                        )
                        withdraw_submit = st.form_submit_button("Withdraw")

                        if withdraw_submit:
                            if withdraw_amount > balance:
                                st.error("Insufficient funds")
                            else:
                                if st.session_state.banking_system.record_transaction(
                                    st.session_state.account_no,
                                    "withdraw",
                                    withdraw_amount,
                                    withdraw_category
                                ):
                                    st.success(f"Successfully withdrew ₹{withdraw_amount:.2f}")
                                    st.rerun()
                                else:
                                    st.error("Failed to process withdrawal")

            # Transfer Money tab
            with tabs[1]:
                with st.form("transfer_form"):
                    st.write("Transfer Money")
                    recipient_account = st.text_input(
                        "Recipient Account Number"
                    ).strip().upper()
                    transfer_amount = st.number_input(
                        "Amount (₹)", 
                        min_value=0.01, 
                        step=0.01
                    )
                    transfer_submit = st.form_submit_button("Transfer")

                    if transfer_submit:
                        if transfer_amount > balance:
                            st.error("Insufficient funds")
                        else:
                            success, message = st.session_state.banking_system.transfer_money(
                                st.session_state.account_no,
                                recipient_account,
                                transfer_amount
                            )
                            if success:
                                st.success(message)
                                st.rerun()
                            else:
                                st.error(message)

            # Loans tab
            with tabs[2]:
                col1, col2 = st.columns(2)

                with col1:
                    st.subheader("Apply for Loan")
                    with st.form("loan_application"):
                        loan_amount = st.number_input(
                            "Loan Amount (₹)", 
                            min_value=1000.0, 
                            step=1000.0
                        )
                        loan_term = st.selectbox(
                            "Loan Term (months)",
                            [12, 24, 36, 48, 60]
                        )
                        interest_rate = st.number_input(
                            "Interest Rate (%)",
                            min_value=5.0,
                            max_value=15.0,
                            value=10.0,
                            step=0.1
                        )
                        loan_submit = st.form_submit_button("Apply")

                        if loan_submit:
                            success, message = st.session_state.banking_system.apply_for_loan(
                                st.session_state.account_no,
                                loan_amount,
                                loan_term,
                                interest_rate
                            )
                            if success:
                                st.success(message)
                                st.rerun()
                            else:
                                st.error(message)

                with col2:
                    st.subheader("Active Loans")
                    active_loans = st.session_state.banking_system.get_active_loans(
                        st.session_state.account_no
                    )

                    if active_loans:
                        for loan in active_loans:
                            with st.expander(f"Loan #{loan[0]} - ₹{loan[1]:,.2f}"):
                                st.write(f"Interest Rate: {loan[2]}%")
                                st.write(f"Term: {loan[3]} months")
                                st.write(f"Monthly Payment: ₹{loan[4]:,.2f}")
                                st.write(f"Remaining Amount: ₹{loan[5]:,.2f}")
                                st.write(f"Next Payment Date: {loan[7]}")

                                with st.form(f"loanpayment{loan[0]}"):
                                    payment_amount = st.number_input(
                                        "Payment Amount (₹)",
                                        min_value=0.01,
                                        max_value=float(loan[5]),
                                        value=float(loan[4]),
                                        step=0.01
                                    )
                                    if st.form_submit_button("Make Payment"):
                                        success, message = st.session_state.banking_system.make_loan_payment(
                                            loan[0],
                                            payment_amount
                                        )
                                        if success:
                                            st.success(message)
                                            st.rerun()
                                        else:
                                            st.error(message)
                    else:
                        st.info("No active loans")

            # Transaction History tab
            with tabs[3]:
                transactions = st.session_state.banking_system.get_transaction_history(
                    st.session_state.account_no
                )

                if transactions:
                    df = pd.DataFrame(
                        transactions,
                        columns=['Type', 'Amount', 'Timestamp', 'Category', 'Transfer Account']
                    )

                    tab1, tab2, tab3 = st.tabs([
                        "Transaction History",
                        "Category Analysis",
                        "Monthly Trends"
                    ])

                    with tab1:
                        st.dataframe(df)

                    with tab2:
                        expenses_by_category = df[
                            df['Type'] == 'withdraw'
                        ].groupby('Category')['Amount'].sum()

                        if not expenses_by_category.empty:
                            fig = px.pie(
                                values=expenses_by_category.values,
                                names=expenses_by_category.index,
                                title='Expenses by Category'
                            )
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.info("No expense data available yet")

                    with tab3:
                        df['Month'] = pd.to_datetime(df['Timestamp']).dt.strftime('%Y-%m')
                        monthly_summary = df.groupby(['Month', 'Type'])['Amount'].sum().unstack()

                        if not monthly_summary.empty:
                            fig = go.Figure()
                            if 'deposit' in monthly_summary.columns:
                                fig.add_trace(go.Bar(
                                    x=monthly_summary.index,
                                    y=monthly_summary['deposit'],
                                    name='Deposits',
                                    marker_color='green'
                                ))
                            if 'withdraw' in monthly_summary.columns:
                                fig.add_trace(go.Bar(
                                    x=monthly_summary.index,
                                    y=monthly_summary['withdraw'],
                                    name='Withdrawals',
                                    marker_color='red'
                                ))
                            fig.update_layout(
                                title='Monthly Transaction Summary',
                                barmode='group'
                            )
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.info("No monthly trend data available yet")
                else:
                    st.info("No transactions recorded yet")

if __name__ == "__main__":
    main()