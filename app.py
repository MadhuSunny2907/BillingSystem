from flask import Flask, render_template, request, send_file, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from fpdf import FPDF
import io
import re
from itertools import zip_longest
import os

app = Flask(__name__)

# ---------------- Google Sheets setup ----------------
sa_json = os.getenv("SERVICE_ACCOUNT_JSON")
with open("/tmp/service_account.json", "w") as f:
    f.write(sa_json)
SPREADSHEET_NAME = "BillingSystem"
INVOICES_WS = "Invoices"
ITEMS_WS = "Invoice_Items"
PRODUCTS_WS = "Items_Sheet"

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("/tmp/service_account.json", scope)
client = gspread.authorize(creds)

SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME", "BillingSystem")
ss = client.open(SPREADSHEET_NAME)
invoices_sheet = ss.worksheet(INVOICES_WS)
items_sheet = ss.worksheet(ITEMS_WS)
products_sheet = ss.worksheet(PRODUCTS_WS)

# ---------------- Helper Functions ----------------
def generate_invoice_number():
    year_short = datetime.now().strftime("%y")
    col = invoices_sheet.col_values(1)[1:]
    seqs = []
    pattern = re.compile(rf"^{year_short}-(\d{{6}})$")
    for val in col:
        m = pattern.match(val.strip())
        if m:
            seqs.append(int(m.group(1)))
    next_seq = max(seqs) + 1 if seqs else 1
    return f"{year_short}-{next_seq:06d}"

def create_pdf_stream(data):
    pdf = FPDF('P', 'mm', 'A4')
    pdf.add_page()
    
    # Add a custom font that supports Indian characters, if needed
    # You will need to place the DejaVuSans.ttf file in a 'static/fonts' folder in your project
    try:
        pdf.add_font('DejaVu', '', 'static/fonts/DejaVuSans.ttf', uni=True)
        pdf.set_font('DejaVu', '', 12)
    except RuntimeError:
        print("DejaVuSans.ttf not found. Using default font.")
        pdf.set_font('Arial', '', 12)

    # Header section with company name and invoice title
    pdf.set_fill_color(52, 152, 219)
    pdf.rect(0, 0, 210, 30, 'F')
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Arial', 'B', 24)
    pdf.cell(0, 20, 'LAXMI uPVC', 0, 0, 'L')
    pdf.cell(0, 20, 'INVOICE', 0, 1, 'R')

    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)

    # Address and details
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 5, 'Bellampalli, Telangana', 0, 1)
    pdf.cell(0, 5, 'Mobile: 1234567890', 0, 1) # Add your mobile number here

    # Customer and invoice info
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 7, 'BILL TO:', 0, 1)
    
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 7, f"Customer Name: {data['customer']}", 0, 0)
    pdf.cell(0, 7, f"Date: {data['date']}", 0, 1, 'R')
    pdf.cell(0, 7, f"Mobile: {data['mobile']}", 0, 0)
    pdf.cell(0, 7, f"Invoice #: {data['invoice_no']}", 0, 1, 'R')
    pdf.cell(0, 7, f"City: {data['city']}", 0, 1)

    pdf.ln(10)

    # Table header
    pdf.set_fill_color(52, 152, 219)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Arial', 'B', 12)
    
    col_widths = [10, 80, 30, 30, 40]
    
    pdf.cell(col_widths[0], 10, 'S.No', 1, 0, 'C', 1)
    pdf.cell(col_widths[1], 10, 'Description', 1, 0, 'C', 1)
    pdf.cell(col_widths[2], 10, 'Qty', 1, 0, 'C', 1)
    pdf.cell(col_widths[3], 10, 'Rate', 1, 0, 'C', 1)
    pdf.cell(col_widths[4], 10, 'Total', 1, 1, 'C', 1)

    # Table rows
    pdf.set_text_color(0, 0, 0)
    pdf.set_font('Arial', '', 12)
    for i, it in enumerate(data["items"], 1):
        item_name = it['item'][:30] + '...' if len(it['item']) > 30 else it['item']
        pdf.cell(col_widths[0], 10, str(i), 1, 0, 'C')
        pdf.cell(col_widths[1], 10, item_name, 1)
        pdf.cell(col_widths[2], 10, str(it['quantity']), 1, 0, 'C')
        pdf.cell(col_widths[3], 10, f"{it['amount']:.2f}", 1, 0, 'R')
        pdf.cell(col_widths[4], 10, f"{it['quantity']*it['amount']:.2f}", 1, 1, 'R')

    pdf.ln(10)
    
    # Totals section
    pdf.cell(0, 5, '', 0, 1)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, f"Total Amount: Rs. {data['total_amount']:.2f}", 0, 1, 'R')
    pdf.cell(0, 10, f"Amount Paid: Rs. {data['amount_paid']:.2f}", 0, 1, 'R')
    pdf.set_fill_color(52, 152, 219)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, f"Balance Due: Rs. {data['balance']:.2f}", 1, 1, 'R', 1)

    pdf.ln(10)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font('Arial', 'I', 10)
    pdf.cell(0, 5, 'Thank you for your business!', 0, 1, 'C')

    # Create the PDF stream and return
    stream = io.BytesIO(pdf.output(dest="S").encode("latin-1"))
    stream.seek(0)
    return stream

# ---------------- Routes ----------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/get_items")
def get_items():
    """Return all items with price from Google Sheet."""
    records = products_sheet.get_all_records()
    return jsonify(records)

@app.route("/save_invoice", methods=["POST"])
def save_invoice():
    customer = request.form.get("customer", "").strip()
    mobile = request.form.get("mobile", "").strip()
    city = request.form.get("city", "").strip()
    items = request.form.getlist("item[]")
    qtys = request.form.getlist("quantity[]")
    amounts = request.form.getlist("amount[]")

    rows = []
    for item, qty, amt in zip_longest(items, qtys, amounts, fillvalue="0"):
        q = int(float(qty)) if qty else 0
        clean_amt = re.sub(r"[^\d.]", "", amt)
        a = float(clean_amt) if clean_amt else 0.0
        rows.append({"item": item, "quantity": q, "amount": a})

    total = sum(r["quantity"] * r["amount"] for r in rows)
    paid = float(request.form.get("amount_paid", "0"))
    balance = total - paid
    invoice_no = generate_invoice_number()
    date = datetime.now().strftime("%Y-%m-%d")

    # Save to Google Sheets
    invoices_sheet.append_row([invoice_no, date, customer, mobile, city, f"{total:.2f}", f"{paid:.2f}", f"{balance:.2f}"])
    for r in rows:
        items_sheet.append_row([invoice_no, r["item"], r["quantity"], f"{r['amount']:.2f}"])

    pdf_stream = create_pdf_stream({
        "invoice_no": invoice_no,
        "date": date,
        "customer": customer,
        "mobile": mobile,
        "city": city,
        "items": rows,
        "total_amount": total,
        "amount_paid": paid,
        "balance": balance
    })
    return send_file(pdf_stream, as_attachment=True, download_name=f"{invoice_no}.pdf")

@app.route("/fetch_invoice")
def fetch_invoice():
    invoice_no = request.args.get("invoice_no", "").strip()
    mobile_search = request.args.get("mobile", "").strip()
    
    records = invoices_sheet.get_all_records()
    record = None
    
    if invoice_no:
        record = next((r for r in records if r["Invoice_No"] == invoice_no), None)
    if not record and mobile_search:
        record = next((r for r in records if r["Mobile"] == mobile_search), None)
    
    if not record:
        return jsonify({"error": "Invoice not found or incorrect details."})

    items = items_sheet.get_all_records()
    item_rows = [r for r in items if r["Invoice_No"] == record["Invoice_No"]]

    return jsonify({
        "invoice_no": record["Invoice_No"],
        "customer": record["Customer_Name"],
        "mobile": record["Mobile"],
        "city": record["City"],
        "amount_paid": float(record["Amount_paid"]),
        "total_amount": float(record["Total_Amount"]),
        "balance": float(record["Balance_Amount"]),
        "items": [
            {
                "item": r["Item"],
                "quantity": int(r["Quantity"]),
                "amount": float(r["Amount"])
            }
            for r in item_rows
        ]
    })

@app.route("/update_invoice", methods=["POST"])
def update_invoice():
    invoice_no = request.form.get("invoice_no", "").strip()
    customer = request.form.get("customer", "")
    mobile = request.form.get("mobile", "")
    city = request.form.get("city", "")
    items = request.form.getlist("item[]")
    qtys = request.form.getlist("quantity[]")
    amounts = request.form.getlist("amount[]")

    rows = []
    total = 0
    for item, qty, amt in zip(items, qtys, amounts):
        q = int(qty) if qty else 0
        a = float(amt) if amt else 0.0
        total += q * a
        rows.append({"item": item, "quantity": q, "amount": a})

    paid = float(request.form.get("amount_paid", "0"))
    balance = total - paid

    # Update invoices sheet
    all_data = invoices_sheet.get_all_values()
    for idx, row in enumerate(all_data):
        if row[0] == invoice_no:
            sheet_row = idx + 1
            invoices_sheet.update(f"C{sheet_row}", [[customer]])
            invoices_sheet.update(f"D{sheet_row}", [[mobile]])
            invoices_sheet.update(f"E{sheet_row}", [[city]])
            invoices_sheet.update(f"F{sheet_row}", [[f"{total:.2f}"]])
            invoices_sheet.update(f"G{sheet_row}", [[f"{paid:.2f}"]])
            invoices_sheet.update(f"H{sheet_row}", [[f"{balance:.2f}"]])
            break

    # Update items sheet: remove old, add new
    all_items = items_sheet.get_all_values()
    header = all_items[0]
    rest = all_items[1:]
    keep = [r for r in rest if r[0] != invoice_no]
    new_rows = [[invoice_no, r["item"], r["quantity"], f"{r['amount']:.2f}"] for r in rows]

    items_sheet.clear()
    items_sheet.append_row(header)
    if keep:
        items_sheet.append_rows(keep)
    if new_rows:
        items_sheet.append_rows(new_rows)

    return "Invoice updated successfully"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))