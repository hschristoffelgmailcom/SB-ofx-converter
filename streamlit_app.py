import streamlit as st
import pdfplumber
from datetime import datetime
import pandas as pd
from docx import Document
import io

def format_amount(val):
    val = val.replace('.', '').replace(',', '.')
    return float(val.strip('-')) * (-1 if '-' in val else 1)

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
    for t in transactions:
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

def extract_transactions_from_docx(docx_file):
    transactions = []
    doc = Document(io.BytesIO(docx_file.read()))
    st.subheader("🛠 DOCX Debug Preview")
    for para in doc.paragraphs:
        line = para.text.strip()
        if not line or line.startswith("Details") or line.startswith("Page"):
            continue
        st.code(f"LINE: {line}")
        parts = line.split()
        st.code(f"PARTS: {parts}")
        if len(parts) >= 6:
            try:
                balance = parts[-1]
                date_str = parts[-2]
                credit = parts[-3] if parts[-3] != '-' else ''
                debit = parts[-4] if parts[-4] != '-' else ''
                fee = parts[-5] if parts[-5] != '-' else ''
                desc = ' '.join(parts[:-5])

                dt = datetime.strptime(date_str.strip(), "%m %d").replace(year=datetime.now().year)
                amount = debit or credit or fee

                transactions.append({
                    "date": dt.strftime("%Y%m%d"),
                    "amount": format_amount(amount),
                    "desc": desc.strip(),
                    "type": "DEBIT" if '-' in amount else "CREDIT",
                    "id": dt.strftime("%Y%m%d") + str(len(transactions))
                })
            except Exception as e:
                continue
    return transactions

st.title("Standard Bank PDF/DOCX to OFX Converter")

uploaded_file = st.file_uploader("Upload your Standard Bank statement (PDF or DOCX)", type=["pdf", "docx"])

if uploaded_file:
    file_type = uploaded_file.name.lower().split(".")[-1]
    if file_type == "docx":
        txns = extract_transactions_from_docx(uploaded_file)
    else:
        with pdfplumber.open(uploaded_file) as pdf:
            st.subheader("🛠 Debug View – Extracted Lines and Parts")
            for page_num, page in enumerate(pdf.pages, start=1):
                st.markdown(f"**Page {page_num}:**")
                text = page.extract_text()
                if text:
                    lines = text.splitlines()
                    for i, line in enumerate(lines[:20]):
                        st.code(f"LINE: {line}")
                        parts = line.split()
                        st.code(f"PARTS: {parts}")

        @st.cache_data
        def extract_transactions(pdf_file):
            transactions = []
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if not text:
                        continue
                    lines = text.splitlines()
                    for line in lines:
                        parts = line.split()
                        if len(parts) < 6:
                            continue
                        try:
                            balance = parts[-1]
                            date_str = parts[-2]
                            credit = parts[-3] if parts[-3] != '-' else ''
                            debit = parts[-4] if parts[-4] != '-' else ''
                            fee = parts[-5] if parts[-5] != '-' else ''
                            desc = ' '.join(parts[:-5])

                            if not date_str:
                                continue
                            dt = datetime.strptime(date_str.strip(), "%m %d").replace(year=datetime.now().year)

                            amount = debit or credit or fee
                            if not amount:
                                continue

                            transactions.append({
                                "date": dt.strftime("%Y%m%d"),
                                "amount": format_amount(amount),
                                "desc": desc.strip(),
                                "type": "DEBIT" if '-' in amount else "CREDIT",
                                "id": dt.strftime("%Y%m%d") + str(len(transactions))
                            })
                        except Exception as e:
                            continue
            return transactions

        txns = extract_transactions(uploaded_file)

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
