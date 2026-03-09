import pandas as pd
import sqlite3

# Chemin du CSV
csv_path = r"E:\DOCUMENT\229 VOITURES\Projet\229Voitures AI Agent\data\car_price_prediction_with_missing.csv"

# Charger le dataset
df = pd.read_csv(csv_path)

# Vérifier colonnes (optionnel)
print(df.columns)
print(df.head())

# Préparer données pour SQLite
df_sql = pd.DataFrame()

df_sql['brand'] = df['Brand']
df_sql['model'] = df['Model']
df_sql['year'] = df['Year']
df_sql['price'] = df['Price']
df_sql['fuel_type'] = df['Fuel Type']
df_sql['transmission'] = df['Transmission']
df_sql['mileage'] = df['Mileage']
df_sql['consumption'] = 0
df_sql['location'] = 'Unknown'
df_sql['description'] = df['Condition']

# Connexion SQLite
db_path = r"E:\DOCUMENT\229 VOITURES\Projet\229Voitures AI Agent\vehicles.db"
conn = sqlite3.connect(db_path)

# Insérer dans la table vehicles
df_sql.to_sql('vehicles', conn, if_exists='append', index=False)

conn.close()

print("Import terminé dans SQLite !")