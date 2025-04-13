import streamlit as st
import pdfplumber
from datetime import datetime
import pandas as pd
from docx import Document
import io
import re

def format_amount(val):
    val = val.replace('.', '').replace(',', '.')
    return float(val.strip('-')) * (-1 if '-' in val else 1)

def extract_year_from_lines(lines):
    date_pattern = re.compile(r"\b(\d{2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b", re.IGNORECASE)
    for line in lines:
        match = date_pattern.search(line)
        if match:
            return int(match.group(3))
    return 2024

def convert_to_ofx(transactions, account_id="021386404", bank_id="STANDARD_BANK"):
    now = datetime.now().strftime("%Y%m%d%H%M%S")
    header = f"""
OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX>
  <SIGNONMSGSRSV1>
    <SONRS>
      <STATUS>
        <CODE>0</CODE>
        <SEVERITY>INFO</SEVERITY>
      </STATUS>
      <DTSERVER>{now}</DTSERVER>
      <LANGUAGE>ENG</LANGUAGE>
    </SONRS>
  </SIGNONMSGSRSV1>
  <BANKMSGSRSV1>
    <STMTTRNRS>
      <TRNUID>1</TRNUID>
      <STATUS>
        <CODE>0</CODE>
        <SEVERITY>INFO</SEVERITY>
      </STATUS>
      <STMTRS>
        <CURDEF>ZAR</CURDEF>
        <BANKACCTFROM>
          <BANKID>{bank_id}</BANKID>
          <ACCTID>{account_id}</ACCTID>
          <ACCTTYPE>CHECKING</ACCTTYPE>
        </BANKACCTFROM>
        <BANKTRANLIST>
"""

    body = ""
    for idx, t in enumerate(transactions, start=1):
        body += f"""
          <STMTTRN>
            <TRNTYPE>{t['type']}</TRNTYPE>
            <DTPOSTED>{t['date']}</DTPOSTED>
            <TRNAMT>{t['amount']}</TRNAMT>
            <FITID>{t['id']}</FITID>
            <NAME>{t['desc']}</NAME>
          </STMTTRN>
"""

    footer = f"""
        </BANKTRANLIST>
        <LEDGERBAL>
          <BALAMT>0.00</BALAMT>
          <DTASOF>{now}</DTASOF>
        </LEDGERBAL>
      </STMTRS>
    </STMTTRNRS>
  </BANKMSGSRSV1>
</OFX>
"""
    return header + body + footer

def extract_transactions_from_lines(pdf_lines, show_debug):
    transactions = []
    year = extract_year_from_lines(pdf_lines)
    skip_next = False
    for i in range(len(pdf_lines) - 1):
        if skip_next:
            skip_next = False
            continue

        line = pdf_lines[i].strip()
        next_line = pdf_lines[i + 1].strip()
        parts = line.split()
        if len(parts) < 6:
            continue

        try:
            balance = parts[-1]
            date_str = f"{parts[-3]} {parts[-2]}"
            dt = datetime.strptime(date_str, "%m %d").replace(year=year)
            amount = parts[-4]
            desc = ' '.join(parts[:-5]) + " " + next_line
            if "BALANCE BROUGHT FORWARD" in desc.upper():
                continue
            transactions.append({
                "date": dt.strftime("%Y%m%d"),
                "amount": format_amount(amount),
                "desc": desc.strip(),
                "type": "DEBIT" if '-' in amount else "CREDIT",
                "id": dt.strftime("%Y%m%d") + str(i + 1)
            })
            skip_next = True
        except:
            continue
    return transactions

def extract_fnb_transactions(pdf_lines, show_debug):
    transactions = []
    date_regex = re.compile(r"\d{2}/\d{2}/\d{4}")
    amount_regex = re.compile(r"^-?[\d.,]+$")
    year = extract_year_from_lines(pdf_lines)

    i = 0
    while i < len(pdf_lines):
        line = pdf_lines[i].strip()
        parts = line.split()
        if not parts or not date_regex.match(parts[0]):
            i += 1
            continue

        try:
            date_str = parts[0]
            dt = datetime.strptime(date_str, "%d/%m/%Y")
            amount_str = parts[-2]
            balance_str = parts[-1]
            desc = ' '.join(parts[1:-2]).strip()

            if i + 1 < len(pdf_lines):
                next_line = pdf_lines[i + 1].strip()
                next_parts = next_line.split()
                if next_parts and not date_regex.match(next_parts[0]) and not amount_regex.match(next_parts[-1]):
                    desc += " " + next_line
                    i += 1

            transactions.append({
                "date": dt.strftime("%Y%m%d"),
                "amount": format_amount(amount_str),
                "desc": desc.strip(),
                "type": "DEBIT" if '-' in amount_str else "CREDIT",
                "id": dt.strftime("%Y%m%d") + str(i + 1)
            })

            if show_debug:
                st.code(f"FNB TXN: {dt.strftime('%Y-%m-%d')} | {amount_str} | {desc}")

        except Exception as e:
            if show_debug:
                st.warning(f"Skipped line {i}: {line} → Error: {e}")
        i += 1

    return transactions

# --- Streamlit App ---
st.title("Bank Statement to OFX Converter")

bank = st.selectbox("Select your bank", ["Standard Bank", "FNB"])

uploaded_file = st.file_uploader("Upload your bank statement (PDF or DOCX)", type=["pdf", "docx"])
show_debug = st.checkbox("Show debug view")

if uploaded_file:
    file_type = uploaded_file.name.lower().split(".")[-1]
    if file_type == "pdf":
        with pdfplumber.open(uploaded_file) as pdf:
            lines = []
            if show_debug:
                st.subheader("🛠 Debug View – Extracted Lines and Parts")
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if text:
                    page_lines = text.splitlines()
                    lines.extend(page_lines)
                    if show_debug:
                        st.markdown(f"**Page {page_num}:**")
                        for line in page_lines:
                            st.code(f"LINE: {line}")
                            st.code(f"PARTS: {line.split()}")

        if bank == "Standard Bank":
            txns = extract_transactions_from_lines(lines, show_debug)
        elif bank == "FNB":
            txns = extract_fnb_transactions(lines, show_debug)
        else:
            txns = []

        if txns:
            df = pd.DataFrame(txns)
            df.index = df.index + 1
            st.success(f"Extracted {len(txns)} transactions.")
            st.dataframe(df[["date", "type", "amount", "desc"]])

            total_debits = df[df['type'] == 'DEBIT']['amount'].sum()
            total_credits = df[df['type'] == 'CREDIT']['amount'].sum()
            difference = total_credits + total_debits

            st.markdown("### 💰 Transaction Totals")
            st.write(f"**Total Debits:** R{abs(total_debits):,.2f}")
            st.write(f"**Total Credits:** R{total_credits:,.2f}")
            st.write(f"**Difference (Credits - Debits):** R{difference:,.2f}")

            ofx_data = convert_to_ofx(txns)
            st.download_button(
                label="Download OFX File",
                data=ofx_data,
                file_name="statement.ofx",
                mime="application/xml"
            )
        else:
            st.error("No transactions found in the uploaded file.")
