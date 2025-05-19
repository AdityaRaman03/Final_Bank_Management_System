import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from Firebase_code import BankingSystem

st.set_page_config(page_title="SecureBank System", layout="wide")

if 'banking_system' not in st.session_state:
    st.session_state.banking_system = BankingSystem()

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

bs = st.session_state.banking_system

def login_screen():
    st.title("SecureBank Login")
    tabs = st.tabs(["Login", "Create Account"])

    with tabs[0]:
        with st.form("login_form"):
            account_no = st.text_input("Account Number").strip().upper()
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")

            if submit:
                user = bs.validate_login(account_no, password)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.account_no = account_no
                    st.session_state.user_name = user[1]
                    st.rerun()
                else:
                    st.error("Invalid credentials")

    with tabs[1]:
        with st.form("create_form"):
            name = st.text_input("Name")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            confirm = st.text_input("Confirm Password", type="password")
            submit = st.form_submit_button("Create Account")

            if submit:
                if password != confirm:
                    st.error("Passwords do not match")
                else:
                    try:
                        acc_no = bs.create_account(name, password, email)
                        st.success(f"Account created! Your account number is: {acc_no}")
                    except Exception as e:
                        st.error(str(e))

def dashboard():
    st.button("Logout", on_click=lambda: st.session_state.update({"logged_in": False}))
    name, email, balance, created_at = bs.get_user_details(st.session_state.account_no)

    st.title(f"Welcome, {name}")
    col1, col2, col3 = st.columns(3)
    col1.metric("Balance", f"₹{balance:.2f}")
    col2.metric("Account No", st.session_state.account_no)
    col3.metric("Since", created_at.split("T")[0])

    st.subheader("Banking Services")
    tabs = st.tabs(["Deposit / Withdraw", "Transfer", "Loans", "History"])

    # Initialize flags for deposit and withdraw
    if 'deposit_success' not in st.session_state:
        st.session_state.deposit_success = False
    if 'deposit_error' not in st.session_state:
        st.session_state.deposit_error = ""

    if 'withdraw_success' not in st.session_state:
        st.session_state.withdraw_success = False
    if 'withdraw_error' not in st.session_state:
        st.session_state.withdraw_error = ""

    if 'transfer_success' not in st.session_state:
        st.session_state.transfer_success = False
    if 'transfer_error' not in st.session_state:
        st.session_state.transfer_error = ""

    if 'loan_success' not in st.session_state:
        st.session_state.loan_success = False
    if 'loan_error' not in st.session_state:
        st.session_state.loan_error = ""

    # For dynamic loan payment flags, use a dictionary
    if 'loan_pay_success' not in st.session_state:
        st.session_state.loan_pay_success = {}
    if 'loan_pay_error' not in st.session_state:
        st.session_state.loan_pay_error = {}

    with tabs[0]:
        col1, col2 = st.columns(2)

        # Deposit form
        with col1.form("deposit_form"):
            amt = st.number_input("Deposit ₹", min_value=0.01)
            cat = st.selectbox("Category", ["Salary", "Other"])
            if st.form_submit_button("Deposit"):
                if bs.record_transaction(st.session_state.account_no, "deposit", amt, cat):
                    st.session_state.deposit_success = True
                    st.session_state.deposit_error = ""
                    st.rerun()
                else:
                    st.session_state.deposit_error = "Deposit failed"
                    st.session_state.deposit_success = False
                    st.rerun()

        if st.session_state.deposit_success:
            st.success("Deposit successful")
            st.session_state.deposit_success = False
        if st.session_state.deposit_error:
            st.error(st.session_state.deposit_error)
            st.session_state.deposit_error = ""

        # Withdraw form
        with col2.form("withdraw_form"):
            amt = st.number_input("Withdraw ₹", min_value=0.01)
            cat = st.selectbox("Category", ["Bills", "Shopping"])
            if st.form_submit_button("Withdraw"):
                if bs.record_transaction(st.session_state.account_no, "withdraw", amt, cat):
                    st.session_state.withdraw_success = True
                    st.session_state.withdraw_error = ""
                    st.rerun()
                else:
                    st.session_state.withdraw_error = "Insufficient funds"
                    st.session_state.withdraw_success = False
                    st.rerun()

        if st.session_state.withdraw_success:
            st.success("Withdraw successful")
            st.session_state.withdraw_success = False
        if st.session_state.withdraw_error:
            st.error(st.session_state.withdraw_error)
            st.session_state.withdraw_error = ""

    with tabs[1]:
        with st.form("transfer_form"):
            to_acc = st.text_input("To Account No").strip().upper()
            amt = st.number_input("Amount ₹", min_value=0.01)
            if st.form_submit_button("Transfer"):
                success, msg = bs.transfer_money(st.session_state.account_no, to_acc, amt)
                if success:
                    st.session_state.transfer_success = True
                    st.session_state.transfer_error = ""
                else:
                    st.session_state.transfer_error = msg
                    st.session_state.transfer_success = False
                st.rerun()

        if st.session_state.transfer_success:
            st.success("Transfer successful")
            st.session_state.transfer_success = False
        if st.session_state.transfer_error:
            st.error(st.session_state.transfer_error)
            st.session_state.transfer_error = ""

    with tabs[2]:
        col1, col2 = st.columns(2)

        with col1.form("loan_form"):
            amt = st.number_input("Loan Amount ₹", min_value=1000.0)
            months = st.selectbox("Term (months)", [12, 24, 36])
            rate = st.slider("Interest %", min_value=5.0, max_value=15.0, value=10.0)
            if st.form_submit_button("Apply"):
                success, msg = bs.apply_for_loan(st.session_state.account_no, amt, months, rate)
                if success:
                    st.session_state.loan_success = True
                    st.session_state.loan_error = ""
                else:
                    st.session_state.loan_error = msg
                    st.session_state.loan_success = False
                st.rerun()

        if st.session_state.loan_success:
            st.success("Loan application successful")
            st.session_state.loan_success = False
        if st.session_state.loan_error:
            st.error(st.session_state.loan_error)
            st.session_state.loan_error = ""

        with col2:
            loans = bs.get_active_loans(st.session_state.account_no)
            for loan in loans:
                with st.expander(f"Loan ₹{loan['amount']}"):
                    st.write(f"Monthly: ₹{loan['monthly_payment']:.2f}")
                    st.write(f"Remaining: ₹{loan['remaining_amount']:.2f}")

                    form_key = f"pay_loan_{loan['loan_id']}"
                    with st.form(form_key):
                        pay_amt = st.number_input(
                            "Pay Amount ₹",
                            min_value=0.01,
                            max_value=loan["remaining_amount"],
                            key=f"pay_amt_{loan['loan_id']}"
                        )
                        if st.form_submit_button("Pay"):
                            success, msg = bs.make_loan_payment(loan["loan_id"], pay_amt)
                            # Store flags in dict by loan_id
                            st.session_state.loan_pay_success[loan['loan_id']] = success
                            if not success:
                                st.session_state.loan_pay_error[loan['loan_id']] = msg
                            else:
                                st.session_state.loan_pay_error[loan['loan_id']] = ""
                            st.rerun()

                    # Show messages for each loan payment
                    if st.session_state.loan_pay_success.get(loan['loan_id'], False):
                        st.success("Loan payment successful")
                        st.session_state.loan_pay_success[loan['loan_id']] = False
                    if st.session_state.loan_pay_error.get(loan['loan_id'], ""):
                        st.error(st.session_state.loan_pay_error[loan['loan_id']])
                        st.session_state.loan_pay_error[loan['loan_id']] = ""

    with tabs[3]:
        transactions = bs.get_transaction_history(st.session_state.account_no)
        
        if transactions:
            df = pd.DataFrame(transactions)

            # Convert timestamp string to datetime UTC
            df['Timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce', utc=True)
            
            df.rename(columns={
                "transaction_type": "Type",
                "amount": "Amount",
                "category": "Category",
                "recipient_account": "Transfer Account"
            }, inplace=True)

            tab1, tab2, tab3 = st.tabs([
                "Transaction History",
                "Category Analysis",
                "Monthly Trends"
            ])

            with tab1:
                st.dataframe(df.drop(columns=["Timestamp"], errors='ignore'))

            with tab2:
                expenses_by_category = df[df['Type'] == 'withdraw'].groupby('Category')['Amount'].sum()

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
                # Parse timestamp
                df['Timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce', utc=True)
                df = df.dropna(subset=['Timestamp'])  # remove rows with invalid dates

                # Normalize and map transaction types
                df['Type'] = df['Type'].str.lower()
                df['Type'] = df['Type'].replace({
                    'loan_disbursement': 'deposit',
                    'loan_payment': 'withdraw'
                })

                # Extract month
                df['Month'] = df['Timestamp'].dt.strftime('%Y-%m')

                # Group and summarize
                monthly_summary = df.groupby(['Month', 'Type'])['Amount'].sum().unstack(fill_value=0)

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
                        xaxis_title='Month',
                        yaxis_title='Amount',
                        barmode='group'
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No monthly trend data available yet")



        else:
            st.info("No transactions found.")



if __name__ == "__main__":
    if not st.session_state.logged_in:
        login_screen()
    else:
        dashboard()
