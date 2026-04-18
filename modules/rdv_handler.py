"""
RDV Handler - 229Voitures
Responsabilite UNIQUE : gerer les formulaires RDV et les leads.
Isole et intouchable.
"""

import sqlite3
import os
import json
import traceback
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "/home/ubuntu/data/229voitures.db")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "paoriellecloud@gmail.com")


def generate_form(vehicle: dict) -> str:
    """Genere le formulaire HTML de demande de RDV."""
    if not vehicle:
        return ""

    year = vehicle.get("year", "")
    make = vehicle.get("make", "")
    model = vehicle.get("model", "")
    dealer = vehicle.get("dealer_name", "Concessionnaire")
    city = vehicle.get("city", "")
    stock = vehicle.get("stock_number", "")
    vin = vehicle.get("vin", "")
    price = vehicle.get("price", "")
    vehicle_id = vehicle.get("vehicle_id", "")

    title = f"{year} {make} {model}".strip()
    dealer_loc = f"{dealer} · {city}" if city else dealer

    price_str = ""
    if price:
        try:
            price_str = f"{float(price):,.0f} $".replace(",", " ")
        except Exception:
            price_str = str(price)

    return f'''<div class="rdv-form-container" style="background:rgba(30,30,30,0.95);border-radius:12px;padding:24px;margin:12px 0;border:1px solid rgba(250,199,117,0.3);max-width:480px;">
  <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#FAC775;margin-bottom:8px;">DEMANDE DE RENDEZ-VOUS</div>
  <div style="font-size:18px;font-weight:600;color:#f0f0f0;margin-bottom:4px;">{title}</div>
  <div style="font-size:13px;color:#888;margin-bottom:20px;">{dealer_loc}</div>
  <input type="hidden" id="rdv_stock" value="{stock}">
  <input type="hidden" id="rdv_vin" value="{vin}">
  <input type="hidden" id="rdv_vehicle_id" value="{vehicle_id}">
  <input type="hidden" id="rdv_price" value="{price_str}">
  <input type="hidden" id="rdv_dealer" value="{dealer}">
  <input type="hidden" id="rdv_vehicle_title" value="{title}">
  <div style="margin-bottom:14px;">
    <label style="display:block;font-size:11px;color:#aaa;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;">PRÉNOM ET NOM *</label>
    <input id="rdv_nom" type="text" autocomplete="name" placeholder="Votre nom complet" style="width:100%;background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.15);border-radius:8px;padding:10px 14px;color:#f0f0f0;font-size:14px;box-sizing:border-box;">
  </div>
  <div style="margin-bottom:14px;">
    <label style="display:block;font-size:11px;color:#aaa;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;">TÉLÉPHONE *</label>
    <input id="rdv_tel" type="tel" autocomplete="tel" placeholder="Votre numéro de téléphone" style="width:100%;background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.15);border-radius:8px;padding:10px 14px;color:#f0f0f0;font-size:14px;box-sizing:border-box;">
  </div>
  <div style="margin-bottom:14px;">
    <label style="display:block;font-size:11px;color:#aaa;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;">COURRIEL *</label>
    <input id="rdv_email" type="email" autocomplete="email" placeholder="Votre adresse courriel" style="width:100%;background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.15);border-radius:8px;padding:10px 14px;color:#f0f0f0;font-size:14px;box-sizing:border-box;">
  </div>
  <div style="margin-bottom:20px;">
    <label style="display:block;font-size:11px;color:#aaa;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;">MESSAGE (OPTIONNEL)</label>
    <textarea id="rdv_msg" placeholder="Précisez vos disponibilités ou toute autre question..." style="width:100%;background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.15);border-radius:8px;padding:10px 14px;color:#f0f0f0;font-size:14px;box-sizing:border-box;resize:vertical;min-height:80px;"></textarea>
  </div>
  <button onclick="submitRDV229()" style="width:100%;background:#FAC775;color:#1a1a1a;border:none;border-radius:8px;padding:14px;font-size:15px;font-weight:600;cursor:pointer;">Envoyer ma demande ↗</button>
  <div style="font-size:11px;color:#666;text-align:center;margin-top:10px;">Le concessionnaire vous contactera dans les 24-48h.</div>
</div>'''


def create_lead(lead_data: dict) -> bool:
    """Sauvegarde un lead dans la DB et envoie l'email."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT, email TEXT, phone TEXT,
                vehicle TEXT, price TEXT,
                stock_number TEXT, vin TEXT,
                dealer TEXT, message TEXT,
                created_at TEXT
            )
        """)

        now = datetime.utcnow().isoformat()
        cursor.execute("""
            INSERT INTO leads (name, email, phone, vehicle, price, stock_number, vin, dealer, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            lead_data.get("name", ""),
            lead_data.get("email", ""),
            lead_data.get("phone", ""),
            lead_data.get("vehicle", ""),
            lead_data.get("price", ""),
            lead_data.get("stock_number", ""),
            lead_data.get("vin", ""),
            lead_data.get("dealer", ""),
            lead_data.get("message", ""),
            now,
        ))
        conn.commit()
        conn.close()

        # Envoyer email
        _send_email(lead_data)
        return True

    except Exception as e:
        print(f"[rdv_handler] Erreur create_lead: {e}")
        print(traceback.format_exc())
        return False


def _send_email(lead: dict) -> None:
    """Envoie l'email de notification de lead."""
    try:
        import resend
        resend.api_key = os.getenv("RESEND_API_KEY", "")
        if not resend.api_key:
            return

        name = lead.get("name", "N/D")
        email = lead.get("email", "N/D")
        phone = lead.get("phone", "N/D")
        vehicle = lead.get("vehicle", "N/D")
        price = lead.get("price", "N/D")
        stock = lead.get("stock_number", "N/D")
        vin = lead.get("vin", "N/D")
        dealer = lead.get("dealer", "N/D")
        message = lead.get("message", "—")

        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#1a1a1a;color:#f0f0f0;border-radius:12px;overflow:hidden;">
          <div style="background:#FAC775;padding:20px;text-align:center;">
            <h1 style="margin:0;color:#1a1a1a;font-size:22px;">229 VOITURES</h1>
            <p style="margin:4px 0 0;color:#1a1a1a;font-size:13px;">Nouveau lead client</p>
          </div>
          <div style="padding:24px;">
            <h2 style="color:#FAC775;margin-top:0;">💰 Nouveau client intéressé</h2>
            <table style="width:100%;border-collapse:collapse;">
              <tr style="border-bottom:1px solid #333;"><td style="padding:10px 0;color:#999;width:120px;">Nom</td><td style="font-weight:bold;">{name}</td></tr>
              <tr style="border-bottom:1px solid #333;"><td style="padding:10px 0;color:#999;">Email</td><td><a href="mailto:{email}" style="color:#FAC775;">{email}</a></td></tr>
              <tr style="border-bottom:1px solid #333;"><td style="padding:10px 0;color:#999;">Téléphone</td><td>{phone}</td></tr>
              <tr style="border-bottom:1px solid #333;"><td style="padding:10px 0;color:#999;">Véhicule</td><td style="font-weight:bold;">{vehicle}</td></tr>
              <tr style="border-bottom:1px solid #333;"><td style="padding:10px 0;color:#999;">Prix</td><td>{price}</td></tr>
              <tr style="border-bottom:1px solid #333;"><td style="padding:10px 0;color:#999;">N° Stock</td><td style="font-weight:bold;">{stock}</td></tr>
              <tr style="border-bottom:1px solid #333;"><td style="padding:10px 0;color:#999;">VIN</td><td style="font-family:monospace;">{vin}</td></tr>
              <tr style="border-bottom:1px solid #333;"><td style="padding:10px 0;color:#999;">Concessionnaire</td><td>{dealer}</td></tr>
              <tr><td style="padding:10px 0;color:#999;">Message</td><td>{message}</td></tr>
            </table>
            <p style="color:#666;font-size:12px;margin-top:20px;text-align:center;">Lead généré par 229Voitures AI Agent</p>
          </div>
        </div>
        """

        resend.Emails.send({
            "from": "alerts@229voitures.ca",
            "to": [ADMIN_EMAIL],
            "subject": f"🚗 Nouveau lead: {vehicle} — {name}",
            "html": html,
        })

    except Exception as e:
        print(f"[rdv_handler] Erreur email: {e}")


def generate_confirmation(vehicle: dict, name: str, phone: str, email: str) -> str:
    """Genere le message de confirmation post-RDV."""
    year = vehicle.get("year", "")
    make = vehicle.get("make", "")
    model = vehicle.get("model", "")
    dealer = vehicle.get("dealer_name", "le concessionnaire")
    dealer_phone = vehicle.get("dealer_phone", "")

    title = f"{year} {make} {model}".strip()

    phone_line = f" Vous pouvez aussi les rejoindre au {dealer_phone}." if dealer_phone else ""

    return (
        f"✅ Votre demande de rendez-vous a été envoyée à {dealer} pour le {title}. "
        f"Le concessionnaire vous contactera au {phone} dans les 24-48h. "
        f"Une confirmation sera envoyée à {email}.{phone_line}\n\n"
        f"💡 **Avant de signer quoi que ce soit** — si le concessionnaire vous présente "
        f"une offre ou un contrat, vous pouvez me le téléverser ici pour analyse. "
        f"Je vérifierai s'il y a des frais cachés ou des conditions défavorables."
    )
