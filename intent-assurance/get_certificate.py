import requests
import warnings
import os
from dotenv import load_dotenv

load_dotenv()

ca_location= os.getenv('CA_CERT_LOCATION')


api_url = f'https://kafka.hexa.tid.es/securityAPI/ca-cert'
code=400
while code !=200:
    try:
        response = requests.get(api_url, verify=False)
        code=response.status_code
        if response.status_code == 200:
            # Save the response content to a file
            with open(f'./{ca_location}', "wb") as file:
                file.write(response.content)
            print("Certificate file saved successfully.")
        else:
            print(f"Error: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Request Error: {e}")