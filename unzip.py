import zipfile
import os

zip_path = r"E:\DOCUMENT\229 VOITURES\Projet\229Voitures AI Agent\car_price_dataset.zip"
extract_path = r"E:\DOCUMENT\229 VOITURES\Projet\229Voitures AI Agent\data"

with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    zip_ref.extractall(extract_path)

print("Décompressé dans :", extract_path)
print(os.listdir(extract_path))