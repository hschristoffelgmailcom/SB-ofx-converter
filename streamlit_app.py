FULL CODE CONTINUED FROM EXISTING...

# Function to extract transactions from Standard Bank PDFs

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

# Function to extract transactions from FNB PDFs

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

    if show_debug:
        st.text("\n".join(raw_lines))

    year = extract_fnb_year(raw_lines)
    transactions = []
    date_month_map = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
                      "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}
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
