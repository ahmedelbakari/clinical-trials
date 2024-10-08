import streamlit as st
from dotenv import load_dotenv
import os
import pandas as pd
from PyPDF2 import PdfReader
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain.output_parsers import ResponseSchema, StructuredOutputParser
import json
import re

# Load environment variables
load_dotenv()

def setup_response_parser():
    """Create and return structured output parsers and format instructions."""
    response_schemas = [
        ResponseSchema(name="T Staging", description="Extract the T staging: (T) Staging:"),
        ResponseSchema(name="N Staging", description="Extract the N staging: (N) Staging:"),
        ResponseSchema(name="HR Status", description="Extract the HR status: (ER) Status:"),
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

    3. HR Presence will be detailed in the biopsy or final surgery pathology report. It will mention Allred score, but you can just report either POSITIVE or NEGATIVE.
    4. HER2 Presence: Immunohistochemistry (IHC) will be reported as POSITIVE (3+) or NEGATIVE (0 or 1+). Occasionally it can be 2+, then use FISH report to determine if POSITIVE or NEGATIVE.
    5. Extract the metastasis status

    If the information is insufficient, please indicate that not enough information is present.
    Format your response as follows:
    (T) Staging: [Your Response Here]
    (N) Staging: [Your Response Here]
    (HR) Status: [Your Response Here]
    HER2 Status: [Your Response Here]
    Metastasis Status: [Your Response Here]

    text: {text}
    {format_instructions}
    """
    prompt_template = ChatPromptTemplate.from_template(template_string)
    return prompt_template.format_messages(text=text, format_instructions=format_instructions)

def initialize_chat_client(api_key, model="gpt-3.5-turbo", temperature=0.0):
    """ Initialize the chat client with specified parameters and error handling. """
    try:
        return ChatOpenAI(api_key=api_key, temperature=temperature, model=model)
    except Exception as e:
        st.error(f"Error initializing ChatOpenAI: {str(e)}")
        return None

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

def filter_clinical_trials(df, er_status, her2_status, type):
    """Filter clinical trials based on ER Status, HER2 Presence, and type."""
    filtered_df = df[
        (df['HR'] == er_status) &
        (df['HER2'] == her2_status) &
        (df['TYPE'] == type)
    ]
    return filtered_df

def parse_json_like(text):
    # Remove any leading/trailing whitespace
    text = text.strip()
    
    # Remove any markdown code block indicators
    text = re.sub(r'```json\s*|\s*```', '', text)
    
    # Attempt to parse as-is first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # If that fails, try to fix common issues
    # Enclose property names in double quotes if they're not already
    text = re.sub(r'(\w+)(?=\s*:)', r'"\1"', text)
    
    # Replace single quotes with double quotes
    text = text.replace("'", '"')
    
    # Try to parse again
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # If it still fails, raise an exception with details
        raise ValueError(f"Failed to parse JSON-like string: {str(e)}\nProcessed text: {text}")


def get_api_key():
    """
    Retrieve the API key from environment variables or Streamlit secrets.
    Returns None if the key is not found.
    """
    # First, try to get the API key from environment variables
    api_key = os.getenv('OPENAI_API_KEY')
    
    # If not found in environment variables, try Streamlit secrets
    if not api_key:
        try:
            api_key = st.secrets["OPENAI_API_KEY"]
        except FileNotFoundError:
            # Secrets file not found, which is expected in local development
            pass
        except KeyError:
            # OPENAI_API_KEY not in secrets
            pass
    
    return api_key

def main():
    st.title('Clinical Trial Matcher')
    parser, format_instructions = setup_response_parser()

    api_key = get_api_key()

    if not api_key:
        st.error("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable or add it to your Streamlit secrets.")
        return

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
        type = "Metastatic"
    elif has_surgical == "Yes":
        type = "Adjuvant"
        full_text += " Metastasis is not present."
    else:
        type = "Neoadjuvant"
        full_text += " Metastasis is not present."

    if full_text.strip():
        patient_notes = create_prompt_template(full_text, format_instructions)
        if st.button("Find Matching Clinical Trials"):
            chat_client = initialize_chat_client(api_key)
            if chat_client is None:
                st.error("Failed to initialize chat client. Please check your API key and try again.")
                return

            response = chat_client.invoke(patient_notes)
            if response:
                try:
                    # Use the new parsing function
                    parsed_results = parse_json_like(response.content)
                    parsed_results['type'] = type
                    st.session_state['result'] = parsed_results  # Store structured results

                    # Load clinical trials data
                    csv_path = 'bcm.trial.data - Sheet1.csv'  # Update this path for Streamlit Cloud
                    df_trials = pd.read_csv(csv_path)

                    # Filter clinical trials
                    filtered_trials = filter_clinical_trials(
                        df_trials,
                        parsed_results["HR Status"],
                        parsed_results["HER2 Presence"],
                        parsed_results["type"]
                    )
                    
                    # Display filtered trials
                    if not filtered_trials.empty:
                        st.header("Matched Clinical Trials:")
                        st.dataframe(filtered_trials)
                    else:
                        st.write("No matching clinical trials found.")
                except Exception as e:
                    st.error(f"Error parsing model response: {str(e)}")
                    st.write("Raw model response:")
                    st.write(response.content)
            else:
                st.error("No response from the model, please check your inputs and API settings.")
    else:
        st.write("Please provide the necessary patient data to proceed.")

    st.header("Diagnosis Summary")
    if 'result' in st.session_state:
        st.write("Results:")
        st.json(st.session_state['result'])  # Display parsed results as formatted JSON
    else:
        st.write("Matches will appear here after processing the inputs.")

if __name__ == '__main__':
    main()
