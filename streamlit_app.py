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

def extract_transactions_from_docx(docx_file, show_debug):
    transactions = []
    doc = Document(io.BytesIO(docx_file.read()))
    lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    year = extract_year_from_lines(lines)
    if show_debug:
        st.subheader("🛠 DOCX Debug Preview")
    for i in range(len(lines)):
        line = lines[i]
        parts = line.split()
        if show_debug:
            st.code(f"LINE: {line}")
            st.code(f"PARTS: {parts}")
        if len(parts) < 6:
            continue
        try:
            balance = parts[-1]
            date_str = f"{parts[-3]} {parts[-2]}"
            dt = datetime.strptime(date_str, "%m %d").replace(year=year)
            amount = parts[-4]
            desc_line = lines[i-1] if i > 0 else ""
            desc = desc_line + ' ' + ' '.join(parts[:-5])

            transactions.append({
                "date": dt.strftime("%Y%m%d"),
                "amount": format_amount(amount),
                "desc": desc.strip(),
                "type": "DEBIT" if '-' in amount else "CREDIT",
                "id": dt.strftime("%Y%m%d") + str(len(transactions)+1)
            })
        except:
            continue
    return transactions

st.title("Standard Bank PDF/DOCX to OFX Converter")

uploaded_file = st.file_uploader("Upload your Standard Bank statement (PDF or DOCX)", type=["pdf", "docx"])
show_debug = st.checkbox("Show debug view")

if uploaded_file:
    file_type = uploaded_file.name.lower().split(".")[-1]
    if file_type == "docx":
        txns = extract_transactions_from_docx(uploaded_file, show_debug)
    else:
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
                        for i, line in enumerate(page_lines):
                            st.code(f"LINE: {line}")
                            parts = line.split()
                            st.code(f"PARTS: {parts}")

        @st.cache_data
        def extract_transactions(pdf_lines):
            transactions = []
            year = extract_year_from_lines(pdf_lines)
            for i in range(len(pdf_lines)):
                parts = pdf_lines[i].split()
                if len(parts) < 6:
                    continue
                try:
                    balance = parts[-1]
                    date_str = f"{parts[-3]} {parts[-2]}"
                    dt = datetime.strptime(date_str, "%m %d").replace(year=year)
                    amount = parts[-4]
                    desc_line = pdf_lines[i-1] if i > 0 else ""
                    desc = desc_line + ' ' + ' '.join(parts[:-5])

                    transactions.append({
                        "date": dt.strftime("%Y%m%d"),
                        "amount": format_amount(amount),
                        "desc": desc.strip(),
                        "type": "DEBIT" if '-' in amount else "CREDIT",
                        "id": dt.strftime("%Y%m%d") + str(len(transactions)+1)
                    })
                except:
                    continue
            return transactions

        txns = extract_transactions(lines)

    if txns:
        df = pd.DataFrame(txns)
        st.success(f"Extracted {len(txns)} transactions.")
        st.dataframe(df[["date", "type", "amount", "desc"]])

        ofx_data = convert_to_ofx(txns)
        st.download_button(
            label="Download OFX File",
            data=ofx_data,
            file_name="standardbank_statement.ofx",
            mime="application/xml"
        )
    else:
        st.error("No transactions found in the uploaded file.")
