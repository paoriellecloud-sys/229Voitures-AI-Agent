import os
import logging

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, html: str) -> bool:
    try:
        import resend
        resend.api_key = os.getenv("RESEND_API_KEY", "")
        if not resend.api_key:
            logger.warning("[email] RESEND_API_KEY manquant")
            return False
        resend.Emails.send({
            "from": "229Voitures <alerts@229voitures.ca>",
            "to": to,
            "subject": subject,
            "html": html
        })
        logger.info(f"[email] Envoyé à {to} — {subject}")
        return True
    except Exception as e:
        logger.error(f"[email] Échec: {e}")
        return False


def send_alert_email(email: str, vehicle: dict) -> bool:
    title = vehicle.get("title", "Véhicule disponible")
    price = vehicle.get("price", 0)
    city = vehicle.get("city", "")
    url = vehicle.get("url", "")
    km = vehicle.get("mileage", "")
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
        <div style="background:#0a0a0a;padding:20px;text-align:center;">
            <h1 style="color:#f5c800;margin:0;">229 VOITURES</h1>
            <p style="color:#888;margin:5px 0;">AI AGENT · CANADA</p>
        </div>
        <div style="padding:30px;background:#f9f9f9;">
            <h2 style="color:#0a0a0a;">🚗 Véhicule correspondant à vos critères !</h2>
            <div style="background:white;border-radius:8px;padding:20px;margin:20px 0;">
                <h3 style="color:#0a0a0a;margin:0 0 10px 0;">{title}</h3>
                <p style="font-size:24px;color:#f5c800;font-weight:bold;margin:5px 0;">{price:,.0f} $</p>
                <p style="color:#666;">📍 {city} | 🔢 {km} km</p>
                {f'<a href="{url}" style="display:inline-block;background:#f5c800;color:#0a0a0a;padding:10px 20px;border-radius:5px;text-decoration:none;font-weight:bold;margin-top:15px;">Voir le véhicule →</a>' if url else ''}
            </div>
            <p style="color:#888;font-size:12px;">229Voitures AI Agent · Achète malin. Négocie mieux.</p>
        </div>
    </div>
    """
    return send_email(email, f"🚗 {title} disponible — {price:,.0f}$", html)


def send_lead_email(dealer_email: str, lead: dict) -> bool:
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
        <div style="background:#0a0a0a;padding:20px;text-align:center;">
            <h1 style="color:#f5c800;margin:0;">229 VOITURES</h1>
            <p style="color:#888;margin:5px 0;">Nouveau lead client</p>
        </div>
        <div style="padding:30px;">
            <h2>💰 Nouveau client intéressé</h2>
            <table style="width:100%;border-collapse:collapse;">
                <tr><td style="padding:8px;border-bottom:1px solid #eee;"><strong>Nom</strong></td><td style="padding:8px;border-bottom:1px solid #eee;">{lead.get('name','')}</td></tr>
                <tr><td style="padding:8px;border-bottom:1px solid #eee;"><strong>Email</strong></td><td style="padding:8px;border-bottom:1px solid #eee;">{lead.get('email','')}</td></tr>
                <tr><td style="padding:8px;border-bottom:1px solid #eee;"><strong>Téléphone</strong></td><td style="padding:8px;border-bottom:1px solid #eee;">{lead.get('phone','')}</td></tr>
                <tr><td style="padding:8px;border-bottom:1px solid #eee;"><strong>Véhicule</strong></td><td style="padding:8px;border-bottom:1px solid #eee;">{lead.get('vehicle_title','')}</td></tr>
                <tr><td style="padding:8px;border-bottom:1px solid #eee;"><strong>Prix</strong></td><td style="padding:8px;border-bottom:1px solid #eee;">{lead.get('vehicle_price','')} $</td></tr>
                <tr><td style="padding:8px;"><strong>Message</strong></td><td style="padding:8px;">{lead.get('message','Aucun message')}</td></tr>
            </table>
            <p style="color:#888;font-size:12px;margin-top:20px;">Lead généré par 229Voitures AI Agent</p>
        </div>
    </div>
    """
    return send_email(dealer_email, f"💰 Nouveau lead — {lead.get('vehicle_title','')}", html)


def send_magic_link_email(email: str, token: str, base_url: str) -> bool:
    link = f"{base_url}/auth/magic?token={token}"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
        <div style="background:#0a0a0a;padding:20px;text-align:center;">
            <h1 style="color:#f5c800;margin:0;">229 VOITURES</h1>
        </div>
        <div style="padding:30px;text-align:center;">
            <h2>Connexion à votre compte</h2>
            <p>Cliquez sur le bouton ci-dessous. Ce lien expire dans 15 minutes.</p>
            <a href="{link}" style="display:inline-block;background:#f5c800;color:#0a0a0a;padding:15px 30px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;margin:20px 0;">Se connecter →</a>
            <p style="color:#888;font-size:12px;">Si vous n'avez pas demandé ce lien, ignorez cet email.</p>
        </div>
    </div>
    """
    return send_email(email, "🔑 Votre lien de connexion 229Voitures", html)


def send_weekly_recap_email(admin_email: str, stats: dict) -> bool:
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
        <div style="background:#0a0a0a;padding:20px;text-align:center;">
            <h1 style="color:#f5c800;margin:0;">229 VOITURES</h1>
            <p style="color:#888;margin:5px 0;">Récapitulatif hebdomadaire</p>
        </div>
        <div style="padding:30px;">
            <h2>📊 Semaine du {stats.get('week','')}</h2>
            <table style="width:100%;border-collapse:collapse;">
                <tr style="background:#f5c800;"><td style="padding:12px;font-weight:bold;">Métrique</td><td style="padding:12px;font-weight:bold;">Valeur</td></tr>
                <tr><td style="padding:10px;border-bottom:1px solid #eee;">💰 Leads cette semaine</td><td style="padding:10px;border-bottom:1px solid #eee;font-weight:bold;">{stats.get('leads_week',0)}</td></tr>
                <tr><td style="padding:10px;border-bottom:1px solid #eee;">💰 Leads ce mois</td><td style="padding:10px;border-bottom:1px solid #eee;font-weight:bold;">{stats.get('leads_month',0)}</td></tr>
                <tr><td style="padding:10px;border-bottom:1px solid #eee;">🔔 Alertes actives</td><td style="padding:10px;border-bottom:1px solid #eee;">{stats.get('alerts',0)}</td></tr>
                <tr><td style="padding:10px;border-bottom:1px solid #eee;">👤 Utilisateurs inscrits</td><td style="padding:10px;border-bottom:1px solid #eee;">{stats.get('users',0)}</td></tr>
                <tr><td style="padding:10px;">🚗 Véhicules en cache</td><td style="padding:10px;">{stats.get('vehicles',0)}</td></tr>
            </table>
        </div>
    </div>
    """
    return send_email(admin_email, f"📊 Récap 229Voitures — {stats.get('leads_week',0)} leads cette semaine", html)
