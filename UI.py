import streamlit as st
import pandas as pd
import pdfplumber
import PyPDF2
import re
from io import BytesIO

# Function to extract details from TDS Returns PDF
def extract_details_from_pdf(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            extracted_text = ""

            # Combine text from all pages
            for page in pdf.pages:
                extracted_text += page.extract_text() or ""

            # Extract specific details
            period_pattern = re.compile(r"period\s+(Q\d)")
            date_range_pattern = re.compile(r"\(From\s+(\d{2}/\d{2}/\d{2})\s+to\s+(\d{2}/\d{2}/\d{2})")
            form_no_box_pattern = re.compile(r"Form\s+No\.\s*(\d{2}\w)", re.IGNORECASE)
            date_pattern = re.compile(r"Date:\s*(\d{2}/\d{2}/\d{4})")

            # Extract Period
            period = period_pattern.search(extracted_text)

            # Extract Date Range
            date_range = date_range_pattern.search(extracted_text)

            # Extract the second occurrence of Form No.
            form_no_matches = form_no_box_pattern.findall(extracted_text)
            form_no = form_no_matches[1] if len(form_no_matches) > 1 else "Not found"

            # Extract Date
            date = date_pattern.search(extracted_text)

            # Format extracted details as a single row DataFrame
            details = {
                "Period": [period.group(1) if period else "Not found"],
                "Date Range": [f"{date_range.group(1)} to {date_range.group(2)}" if date_range else "Not found"],
                "Form No.": [form_no],
                "Date": [date.group(1) if date else "Not found"],
            }

            return pd.DataFrame(details)

    except Exception as e:
        return pd.DataFrame({"Error": [str(e)]})

# Function to extract table from TDS Returns PDF
def extract_table_from_pdf(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            extracted_data = []

            for page in pdf.pages:
                tables = page.extract_tables()

                for table in tables:
                    if table:
                        for row in table:
                            extracted_data.append(row)

            headers = ["Sr. No.", "Return Type", "No. of Deductee / Party Records", "Amount Paid (₹)", "Tax Deducted / Collected (₹)", "Tax Deposited (₹)"]
            table_data = []

            for row in extracted_data:
                if len(row) == len(headers):
                    row_dict = dict(zip(headers, row))
                    table_data.append(row_dict)

            if len(table_data) > 1 and table_data[0]["Sr. No."] == "Sr. No.":
                table_data.pop(0)

            df = pd.DataFrame(table_data)
            df.dropna(subset=headers, how='all', inplace=True)

            return df

    except Exception as e:
        return pd.DataFrame({"Error": [str(e)]})

# Function: Process HDFC Bank PDF
def process_hdfc_bank(pdf_file):
    extracted_text = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            extracted_text += page.extract_text() + "\n"
    return extracted_text

# Function: Parse HDFC Bank Text
def parse_hdfc_bank_text(raw_text):
    lines = raw_text.split("\n")
    return {
        "Date of Receipt": lines[12].split()[-1],
        "Nature of Payment": lines[7].strip().replace("Nature of Payment ", ""),
        "Basic Tax": float(lines[9].replace("Basic Tax", "").strip().replace(",", "")),
        "Interest": float(lines[14].split()[1].replace(",", "")),
        "Penalty": float(lines[12].split()[1].replace(",", "")),
        "Fee (Sec. 234E)": float(lines[15].split()[3].replace(",", "")),
        "TOTAL Amount": float(lines[16].split("Drawn on")[0].replace("TOTAL", "").strip().replace(",", "")),
        "Drawn on": lines[16].split("Drawn on")[-1].strip(),
        "Payment Realisation Date": lines[19].split()[-1],
        "Challan No": int(lines[10].split()[-1].replace(",", "")),
        "Challan Serial No.": int(lines[13].split()[-1].replace(",", ""))
    }

# Function: Process Income Tax PDF
def process_income_tax(pdf_file):
    reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    return text

# Function: Parse Income Tax Text
def parse_income_tax_text(text):
    details = {}
    lines = text.split("\n")
    for line in lines:
        if "Nature of Payment" in line:
            details["Nature of Payment"] = line.split(":")[-1].strip()
        elif "Amount (in Rs.)" in line:
            details["Amount (in Rs.)"] = line.split(":")[-1].strip()
        elif "Challan No" in line:
            details["Challan No."] = line.split(":")[-1].strip()
        elif "Tender Date" in line:
            tender_date_raw = line.split(":")[-1]
            tender_date_cleaned = tender_date_raw.split("Tax Breakup Details")[0].strip()
            details["Tender Date"] = tender_date_cleaned
        elif line.startswith("DInterest"):
            details["Interest"] = line.split("₹")[-1].strip()
        elif line.startswith("EPenalty"):
            details["Penalty"] = line.split("₹")[-1].strip()
        elif line.startswith("FFee under section 234E"):
            details["Fee (Sec. 234E)"] = line.split("₹")[-1].strip()
        elif line.startswith("Total (A+B+C+D+E+F)"):
            details["TOTAL"] = line.split("₹")[-1].strip()
    return details

# Function: Save Data to Excel
def save_to_excel(data_frames):
    output = BytesIO()
    combined_df = pd.concat(data_frames, ignore_index=True)
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        combined_df.to_excel(writer, index=False, sheet_name="Extracted Data", float_format="%.2f")
    output.seek(0)
    return output

# Streamlit App
st.set_page_config(page_title="Challan Data Extraction Tool", layout="wide")
st.title("💼 TDS Challan Data Extraction Tool")

# Sidebar Configuration
st.sidebar.header("🛠️ Process Configuration")
option = st.sidebar.radio(
    "Select Document Type",
    ["TDS Returns", "TDS Payments"],
    help="Choose the type of document for data extraction."
)

if option == "TDS Payments":
    payment_option = st.sidebar.radio(
        "Select Payment Source",
        ["HDFC Bank", "Income Tax Department"],
        help="Choose the type of payment document for processing."
    )

# File uploader with refresh functionality
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []

uploaded_files = st.sidebar.file_uploader(
    "Upload PDF Files",
    type="pdf",
    accept_multiple_files=True,
    key="file_uploader",
    help="Drag and drop or upload PDF files for processing."
)

if uploaded_files:
    st.session_state.uploaded_files = uploaded_files

if st.sidebar.button("🔄 Refresh to Upload New Files"):
    st.session_state.clear()
    st.experimental_rerun()

submit = st.sidebar.button("🚀 Start Extraction")

# Main Processing Section
if submit and st.session_state.uploaded_files:
    st.subheader("🔍 Extracting Data from Uploaded Files")
    progress = st.progress(0)
    extracted_data = []

    # Process files based on the selected option
    for idx, pdf_file in enumerate(st.session_state.uploaded_files):
        try:
            if option == "TDS Returns":
                details_df = extract_details_from_pdf(pdf_file)
                table_df = extract_table_from_pdf(pdf_file)
                combined_df = pd.concat([details_df, table_df], ignore_index=True)
            elif option == "TDS Payments" and payment_option == "HDFC Bank":
                raw_text = process_hdfc_bank(pdf_file)
                parsed_data = parse_hdfc_bank_text(raw_text)
                combined_df = pd.DataFrame([parsed_data])
            elif option == "TDS Payments" and payment_option == "Income Tax Department":
                raw_text = process_income_tax(pdf_file)
                parsed_data = parse_income_tax_text(raw_text)
                combined_df = pd.DataFrame([parsed_data])
            else:
                raise ValueError("Invalid option selected.")

            extracted_data.append(combined_df)

            # Update progress bar
            progress.progress((idx + 1) / len(st.session_state.uploaded_files))
        except Exception as e:
            st.error(f"Error processing '{pdf_file.name}': {e}")

    # Display and download results
    if extracted_data:
        final_combined_df = pd.concat(extracted_data, ignore_index=True)
        st.subheader("📊 Extracted Data")
        st.dataframe(final_combined_df)

        excel_data = save_to_excel([final_combined_df])
        st.download_button(
            label="📅 Download Extracted Data (Excel)",
            data=excel_data,
            file_name="extracted_tds_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("No data was extracted. Please check the uploaded files.")
else:
    st.info("Upload PDF files and click 'Start Extraction' to process your documents.")
