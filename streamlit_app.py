import streamlit as st
import pdfplumber
from datetime import datetime
import pandas as pd
from docx import Document
import io
import re
import fitz  # PyMuPDF for FNB
import pytesseract
from PIL import Image

# Set page config for a modern look
st.set_page_config(page_title="Bank Statement to OFX Converter", layout="centered")

# UI Styling
st.markdown("""
    <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        .stButton>button {
            background-color: #0072E3;
            color: white;
            font-weight: 600;
            padding: 0.6rem 1.2rem;
            border-radius: 8px;
        }
        .stDownloadButton>button {
            background-color: #3BB273;
            color: white;
            font-weight: 600;
            padding: 0.6rem 1.2rem;
            border-radius: 8px;
        }
    </style>
""", unsafe_allow_html=True)

st.title("📄 Bank Statement to OFX Converter")

# Bank selection
bank = st.selectbox("Select your bank", ["Standard Bank", "FNB"])
current_bank = bank

# Upload and settings
uploaded_files = st.file_uploader("Upload one or more bank statements (PDF only)", type=["pdf"], accept_multiple_files=True)
show_debug = st.checkbox("Show debug view")
combine_output = st.checkbox("Combine all into one OFX file")

# Helper functions
def format_amount(val, txn_type=None):
    if current_bank == "FNB":
        val = val.replace("Cr", "").replace(",", "")
    else:
        val = val.replace('.', '').replace(',', '.').replace('Cr', '')
    amount = float(val.strip('-'))
    if txn_type == "DEBIT" or ('-' in val and txn_type is None):
        amount *= -1
    return amount

def extract_year_from_lines(lines):
    for line in lines:
        match = re.search(r"Statement Date\s*:\s*(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", line, re.IGNORECASE)
        if match:
            return int(match.group(3))
    for line in lines:
        match = re.search(r"\b\d{2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b", line, re.IGNORECASE)
        if match:
            return int(match.group(2))
    return 2024

def extract_fnb_year(lines):
    for line in lines:
        match = re.search(r"Statement Date\s*:\s*(\d{1,2})\s+\w+\s+(\d{4})", line)
        if match:
            return int(match.group(2))
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

def extract_standardbank_transactions(pdf_lines, show_debug):
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
            txn_type = "DEBIT" if '-' in amount else "CREDIT"
            transactions.append({
                "date": dt.strftime("%Y%m%d"),
                "amount": format_amount(amount, txn_type),
                "desc": desc.strip(),
                "type": txn_type,
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
        if not text.strip() or len(text.strip()) < 200:
            pix = page.get_pixmap()
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img)
        raw_lines.extend(text.splitlines())
    doc.close()

    year = extract_fnb_year(raw_lines)
    transactions = []
    date_month_map = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06", "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}
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
                date_obj = datetime.strptime(f"{year}{month}{day}", "%Y%m%d")
                desc_line = ' '.join(parts[2:])
                full_desc = desc_line.strip() if desc_line else "UNKNOWN"

                # Scan next few lines for better description if unknown
                if full_desc == "UNKNOWN":
                    for offset in range(1, 3):
                        if i + offset < len(raw_lines):
                            possible_desc = raw_lines[i + offset].strip()
                            if possible_desc and not re.search(r"\d{2} \w{3}", possible_desc):
                                full_desc = possible_desc
                                break

                j = i + 1
                while j < len(raw_lines):
                    next_line = raw_lines[j].strip()
                    if re.search(r"\d{1,3}(,\d{3})*\.\d{2}(Cr)?", next_line):
                        break
                    j += 1
                i = j
                amt_line = raw_lines[i] if i < len(raw_lines) else ""
                amt_match = re.search(r"\d{1,3}(,\d{3})*\.\d{2}(Cr)?", amt_line)
                if amt_match:
                    amt_text = amt_match.group(0)
                    txn_type = "CREDIT" if "Cr" in amt_text else "DEBIT"
                    amount = format_amount(amt_text, txn_type)
                    transactions.append({
                        "date": date_obj.strftime("%Y%m%d"),
                        "amount": amount,
                        "desc": full_desc.strip(),
                        "type": txn_type,
                        "id": date_obj.strftime("%Y%m%d") + str(i + 1)
                    })
                    i += 1
                else:
                    i += 1
            except:
                i += 1
        else:
            i += 1
    return transactions

# Run conversion for each file
all_txns = []
if uploaded_files:
    for uploaded_file in uploaded_files:
        file_name = uploaded_file.name.rsplit('.', 1)[0]
        if bank == "Standard Bank":
            with pdfplumber.open(uploaded_file) as pdf:
                lines = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        lines.extend(text.splitlines())
                txns = extract_standardbank_transactions(lines, show_debug)
        elif bank == "FNB":
            txns = extract_fnb_transactions_from_raw_text(uploaded_file, show_debug)
        else:
            txns = []

        if txns:
            if not combine_output:
                ofx_data = convert_to_ofx(txns)
                st.download_button(
                    label=f"Download {file_name}.ofx",
                    data=ofx_data,
                    file_name=f"{file_name}.ofx",
                    mime="application/xml"
                )
            all_txns.extend(txns)

    if all_txns:
        df = pd.DataFrame(all_txns)
        df.index = df.index + 1
        st.success(f"Extracted {len(all_txns)} total transactions from {len(uploaded_files)} file(s).")
        st.dataframe(df[["date", "type", "amount", "desc"]])

        total_debits = df[df['type'] == 'DEBIT']['amount'].sum()
        total_credits = df[df['type'] == 'CREDIT']['amount'].sum()
        difference = total_credits + total_debits

        st.markdown("### 💰 Total Summary")
        st.write(f"**Total Debits:** R{abs(total_debits):,.2f}")
        st.write(f"**Total Credits:** R{total_credits:,.2f}")
        st.write(f"**Difference:** R{difference:,.2f}")

        if combine_output:
            ofx_data = convert_to_ofx(all_txns)
            st.download_button(
                label="🗅️ Download Combined OFX",
                data=ofx_data,
                file_name="combined_output.ofx",
                mime="application/xml"
            )
    else:
        st.error("No transactions found in the uploaded file(s).")
