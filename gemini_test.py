from google import genai

# Configure la clé API
client = genai.Client(api_key="AIzaSyBkA0OnxgszC00kg9C-UuP3E_SnxCK1k2w")

# Envoyer une requête
response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents="Bonjour, qui es-tu ?"
)

print(response.text)