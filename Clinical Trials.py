import streamlit as st
import requests
import json
import openai
from openai import OpenAI
import os
import pandas as pd

# Initialize Streamlit app
st.title('Clinical Trial Matcher')

# Initialize OpenAI API
client = OpenAI(api_key='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')

# User input for diagnosis
diagnosis = st.text_input("Enter your diagnosis:")

# User input for location
cities = ['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'Philadelphia', 'San Antonio', 'San Diego', 'Dallas', 'San Jose']
city = st.selectbox("Select your city:", cities)

# Initialize DataFrame
df = pd.DataFrame(columns=['Trial ID', 'Condition', 'Brief Title', 'Eligibility', 'Responsible Party Type', 'Investigator Full Name'])

# Button to start the search
if st.button('Find Trials'):
    # Use OpenAI GPT-4 to identify cancer type
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Identify the type of cancer from the given medical diagnosis."},
            {"role": "user", "content": diagnosis}
        ]
    )
    cancer_type = response.choices[0].message.content.strip()
    st.write(f"Identified Cancer Type: {cancer_type}")  # Debug: Print the type of cancer identified by GPT-4

    # Initialize variables for API query
    min_rank = 1
    max_rank = 100

    # Loop to fetch all trials
    while True:
        api_url = f"https://ClinicalTrials.gov/api/query/study_fields?expr={cancer_type}+AND+recruiting+AND+AREA[LocationCity]{city}&fields=EligibilityCriteria,LeadSponsorName,DesignPrimaryPurpose,NCTId,Condition,BriefTitle&min_rnk={min_rank}&max_rnk={max_rank}&fmt=JSON"
        response = requests.get(api_url)
        data = json.loads(response.text)
        
        st.write(f"Querying: {api_url}")  # Debug: Display the URL being accessed
        st.write(f"API Response: {data}")  # Debug: Print the raw API response

        if 'StudyFields' in data['StudyFieldsResponse']:
            for trial in data['StudyFieldsResponse']['StudyFields']:
                new_row = {
                    'Trial ID': trial['NCTId'][0] if 'NCTId' in trial else None,
                    'Condition': trial['Condition'][0] if 'Condition' in trial else None,
                    'Brief Title': trial['BriefTitle'][0] if 'BriefTitle' in trial else None,
                    'Eligibility': trial['EligibilityCriteria'][0] if 'EligibilityCriteria' in trial else None,
                    'Lead Sponsor Name': trial['LeadSponsorName'][0] if 'LeadSponsorName' in trial else None,
                    'Design Primary Purpose': trial['DesignPrimaryPurpose'][0] if 'DesignPrimaryPurpose' in trial else None
                }
                df = df.append(new_row, ignore_index=True)
        else:
            st.write("No more data or error in data retrieval.")
            break

        min_rank += 100
        max_rank += 100
        if max_rank > data['StudyFieldsResponse']['NStudiesFound']:
            break

    # Display the first 25 results
    st.table(df.head(25))

# Run the application with:
# streamlit run <filename>.py
