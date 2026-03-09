from google import genai

client = genai.Client(api_key="AIzaSyBkA0OnxgszC00kg9C-UuP3E_SnxCK1k2w")

models = client.models.list()

for m in models:
    print(m.name)