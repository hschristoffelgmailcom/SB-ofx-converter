import streamlit as st
import pdfplumber
from datetime import datetime
import pandas as pd
from docx import Document
import io
import re
import fitz  # PyMuPDF for FNB

def format_amount(val):
    val = val.replace('.', '').replace(',', '.').replace('Cr', '')
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

def extract_fnb_transactions_from_raw_text(pdf_file, show_debug=False):
    doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
    raw_lines = []
    for page in doc:
        text = page.get_text()
        raw_lines.extend(text.splitlines())
    doc.close()

    transactions = []
    date_month_map = {
        "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
        "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"
    }

    i = 0
    while i < len(raw_lines):
        line = raw_lines[i].strip()
        parts = line.split()

        if show_debug:
            st.code(f"FNB LINE: {line}")

        if len(parts) >= 2 and parts[0].isdigit() and parts[1][:3] in date_month_map:
            try:
                day = parts[0].zfill(2)
                month = date_month_map[parts[1][:3]]
                date_obj = datetime.strptime(f"2024{month}{day}", "%Y%m%d")

                desc_line = ' '.join(parts[2:])
                j = i + 1
                amount = None
                while j < len(raw_lines) and not amount:
                    amt_match = re.search(r"\d{1,3}(,\d{3})*\.\d{2}(Cr)?", raw_lines[j])
                    if amt_match:
                        amt_text = amt_match.group(0)
                        txn_type = "CREDIT" if "Cr" in amt_text else "DEBIT"
                        amount = format_amount(amt_text)
                        break
                    else:
                        desc_line += " " + raw_lines[j].strip()
                    j += 1

                if amount is not None:
                    transactions.append({
                        "date": date_obj.strftime("%Y%m%d"),
                        "amount": amount,
                        "desc": desc_line.strip(),
                        "type": txn_type,
                        "id": date_obj.strftime("%Y%m%d") + str(i + 1)
                    })

                i = j + 1
            except:
                i += 1
        else:
            i += 1
    return transactions

# --- Streamlit App ---
st.title("Bank Statement to OFX Converter")

bank = st.selectbox("Select your bank", ["Standard Bank", "FNB"])

uploaded_file = st.file_uploader("Upload your bank statement (PDF or DOCX)", type=["pdf", "docx"])
show_debug = st.checkbox("Show debug view")

if uploaded_file:
    file_type = uploaded_file.name.lower().split(".")[-1]
    if bank == "Standard Bank" and file_type == "pdf":
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
        txns = extract_transactions_from_lines(lines, show_debug)

    elif bank == "FNB" and file_type == "pdf":
        txns = extract_fnb_transactions_from_raw_text(uploaded_file, show_debug)

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
