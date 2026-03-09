from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

def explain_vehicle(vehicle):
    
    prompt = f"""
    You are a car expert.

    Analyze this vehicle and explain if it is a good deal.

    Vehicle:
    Brand: {vehicle['brand']}
    Model: {vehicle['model']}
    Year: {vehicle['year']}
    Price: {vehicle['price']}
    Mileage: {vehicle['mileage']}

    Explain the advantages and potential risks.
    """

    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt
    )

    return response.text