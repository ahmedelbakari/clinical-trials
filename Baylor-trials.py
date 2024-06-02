import streamlit as st
from dotenv import load_dotenv
import os
from PyPDF2 import PdfReader
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain.output_parsers import ResponseSchema, StructuredOutputParser

# Load environment variables
headers = {
    "authorization": st.secrets["auth_key"],
    "content_type": "application/json"
}

def setup_response_parser():
    """Create and return structured output parsers and format instructions."""
    response_schemas = [
        ResponseSchema(name="T Staging", description="Extract the T staging: (T) Staging:"),
        ResponseSchema(name="N Staging", description="Extract the N staging: (N) Staging:"),
        ResponseSchema(name="ER Status", description="Extract the ER status: (ER) Status:"),
        ResponseSchema(name="HER2 Presence", description="Extract the HER2 presence: HER2 Presence:"),
        ResponseSchema(name="Metastasis Status", description="Extract the Metastasis Presence: Metastasis Presence:"),
    ]
    output_parser = StructuredOutputParser.from_response_schemas(response_schemas)
    format_instructions = output_parser.get_format_instructions()
    return output_parser, format_instructions

def create_prompt_template(text, format_instructions):
    """ Generate a formatted prompt template based on the provided text. """
    template_string = """
    Review the following text to determine TNM staging, Estrogen receptor status (ER), HER2 status. Abide by the following rules derived from AJCC v8. Sometimes the information does not directly mention TNM staging but provide tumor size that could lead to determining the staging, use that when available.

    1. Tumor (T) Staging:
        - T1mi: tumors less than 0.1cm
        - T1a: 0.1 to 0.5 cm
        - T1b: 0.51 to 1 cm
        - T1c: 1.1 to 2 cm
        - T2: 21mm to 50mm
        - T3: bigger than 51mm
        - T4a: cancer has invaded into the chest wall (seen on imaging)
        - T4b: cancer has invaded into the skin
        - T4c: cancer has spread to both the skin and the chest wall
        - T4d: inflammatory carcinoma (reported as inflammatory in the imaging or pathology reports)

    2. Node (N) Staging:
        - pN0: no cancer deposits at all
        - pN1mi: cancer deposit within at least 1 and up to 3 lymph nodes, with deposit size 0.2 to 2mm
        - pN1a: cancer deposit within at least 1 and up to 3 lymph nodes, with deposit size larger than 2mm
        - pN2a: cancer deposits within at least 4 and up to 10 lymph nodes
        - pN3a: cancer deposit within 10 or more lymph nodes
        - cN0: no signs of cancer in the lymph nodes following scans and examination
        - cN1: cancer cells have spread to one or more lymph nodes in the lower or middle part of the armpit
        - cN1mi: cancer cells in the lymph nodes are very small (micrometastases)
        - cN2a: cancer cells in the armpit are stuck together or fixed to other areas of the breast
        - cN2b: cancer cells in the lymph nodes behind the breastbone
        - cN3a: cancer cells in the lymph nodes below the collarbone
        - cN3b: cancer cells in the lymph nodes around the armpit and behind the breastbone
        - cN3c: cancer cells in the lymph nodes above the collarbone

    3. ER Presence will be detailed in the biopsy or final surgery pathology report. It will mention Allred score, but you can just report either POSITIVE or NEGATIVE.
    4. HER2 Presence: Immunohistochemistry (IHC) will be reported as POSITIVE (3+) or NEGATIVE (0 or 1+). Occasionally it can be 2+, then use FISH report to determine if POSITIVE or NEGATIVE.

    If the information is insufficient, please indicate that not enough information is present.
    Format your response as follows:
    (T) Staging: [Your Response Here]
    (N) Staging: [Your Response Here]
    (ER) Status: [Your Response Here]
    HER2 Status: [Your Response Here]
    Metastasis Status: [Your Response Here]

    text: {text}
    {format_instructions}
    """
    prompt_template = ChatPromptTemplate.from_template(template_string)
    return prompt_template.format_messages(text=text, format_instructions=format_instructions)

def initialize_chat_client(api_key, model="gpt-4o", temperature=0.0):
    """ Initialize the chat client with specified parameters. """
    return ChatOpenAI(api_key=api_key, temperature=temperature, model=model)

def extract_text_from_pdf(pdf_file):
    """ Extract text from each page of the provided PDF file. """
    text = ""
    if pdf_file is not None:
        pdf_reader = PdfReader(pdf_file)
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            text += page_text if page_text else " [No text extracted from this page.]"
    return text

def handle_input(label, key_prefix):
    file = st.file_uploader(f"Upload {label}", type=["pdf", "docx", "txt"], key=f"{key_prefix}_file")
    text = st.text_area(f"Or input {label} text", key=f"{key_prefix}_text")
    return file, text

def main():
    load_dotenv()
    api_key = os.getenv('OPENAI_API_KEY')

    st.title('Clinical Trial Matcher')
    parser, format_instructions = setup_response_parser()

    with st.sidebar:
        st.header("Patient Data Input")

        # Sidebar Questionnaire
        has_imaging = st.radio("Do you have an Imaging Report?", ("No", "Yes"), key="has_imaging")
        has_biopsy = st.radio("Do you have a Biopsy Report?", ("No", "Yes"), key="has_biopsy")
        has_surgical = st.radio("Do you have a Surgical Report?", ("No", "Yes"), key="has_surgical")
        metastasis = st.radio("Is there metastasis?", ("No", "Yes"), key="metastasis")

    # Main page inputs based on the questionnaire
    full_text = ""
    if has_imaging == "Yes":
        st.subheader("Imaging Report")
        imaging_file, imaging_text = handle_input("Imaging Report", "imaging")
        full_text += imaging_text if imaging_text else extract_text_from_pdf(imaging_file)

    if has_biopsy == "Yes":
        st.subheader("Biopsy Report")
        biopsy_file, biopsy_text = handle_input("Biopsy Report", "biopsy")
        full_text += biopsy_text if biopsy_text else extract_text_from_pdf(biopsy_file)

    if has_surgical == "Yes":
        st.subheader("Surgical Report")
        surgical_file, surgical_text = handle_input("Surgical Report", "surgical")
        full_text += surgical_text if surgical_text else extract_text_from_pdf(surgical_file)

    if metastasis == "Yes":
        full_text += " Metastasis is present."
        space = "Metastatic"
    elif has_surgical == "Yes":
        space = "Adjuvant"
        full_text += " Metastasis is not present."
    else:
        space = "Neoadjuvant"
        full_text += " Metastasis is not present."

    if full_text.strip():
        patient_notes = create_prompt_template(full_text, format_instructions)
        if st.button("Find Matching Clinical Trials"):
            chat_client = initialize_chat_client(api_key)
            response = chat_client.invoke(patient_notes)
            if response:
                parsed_results = parser.parse(response.content)
                parsed_results['space'] = space
                st.session_state['result'] = parsed_results  # Store structured results
            else:
                st.error("No response from the model, please check your inputs and API settings.")
        else:
            st.error("Please click 'Find Matching Clinical Trials' to proceed.")
    else:
        st.write("Please provide the necessary patient data to proceed.")

    st.header("Matched Clinical Trials")
    if 'result' in st.session_state:
        st.write("Results:")
        st.json(st.session_state['result'])  # Display parsed results as formatted JSON
    else:
        st.write("Matches will appear here after processing the inputs.")

if __name__ == '__main__':
    main()
