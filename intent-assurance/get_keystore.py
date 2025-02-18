import requests
import warnings
import os
from dotenv import load_dotenv

load_dotenv()

keystore_location= os.getenv('KEYSTORE_LOCATION')

# Suppressing warnings from requests
warnings.filterwarnings("ignore")

common_name=os.getenv('COMMON_NAME')

api_url = f'https://kafka.hexa.tid.es/securityAPI/sign-certificate/{common_name}'
code=400
while code !=200:
    response = requests.get(api_url, verify=False)
    code=response.status_code
    if response.status_code == 200:
        # Save the response content to a file
        with open(f'./{keystore_location}', "wb") as file:
            file.write(response.content)
        print("Keystore file saved successfully.")
    else:
        print(f"Error: {response.status_code} - {response.text}")

    api_url = f'https://kafka.hexa.tid.es/securityAPI/ca-cert'
    response = requests.get(api_url,verify=False)