"""Formatters pour les fiches véhicules HTML."""
import re

TPS_RATE = 0.05
TVQ_RATE = 0.09975

COULEUR_HEX = {
    "bleu": "#378ADD",
    "rouge": "#E24B4A",
    "noir": "#2C2C2A",
    "blanc": "#D3D1C7",
    "gris": "#888780",
    "vert": "#639922",
    "argent": "#B4B2A9",
    "brun": "#BA7517",
    "beige": "#FAC775",
    "orange": "#EF9F27",
    "jaune": "#EF9F27",
    "violet": "#7F77DD",
    "mauve": "#7F77DD",
}


def get_statut_prix(prix: float, marche_moyen: float) -> dict:
    if marche_moyen and marche_moyen > 0:
        diff_pct = ((prix - marche_moyen) / marche_moyen) * 100
        if diff_pct <= -5:
            return {"label": "Bon prix", "bg": "#EAF3DE", "color": "#27500A"}
        elif diff_pct <= 5:
            return {"label": "Prix dans la moyenne", "bg": "#FAEEDA", "color": "#633806"}
        else:
            return {"label": "Prix élevé", "bg": "#FCEBEB", "color": "#791F1F"}
    return {"label": "Prix non comparé", "bg": "#F1EFE8", "color": "#5F5E5A"}


def get_couleur_hex(couleur: str) -> str:
    if not couleur:
        return "#888780"
    return COULEUR_HEX.get(couleur.lower().strip(), "#888780")


def calc_taxes(prix: float) -> dict:
    tps = round(prix * TPS_RATE, 2)
    tvq = round(prix * TVQ_RATE, 2)
    total = round(prix + tps + tvq, 2)
    return {
        "tps": f"{tps:,.2f} $".replace(",", "\u00a0"),
        "tvq": f"{tvq:,.2f} $".replace(",", "\u00a0"),
        "total": f"{total:,.2f} $".replace(",", "\u00a0"),
    }


def fmt_prix(val) -> str:
    try:
        return f"{float(val):,.0f}\u00a0$".replace(",", "\u00a0")
    except Exception:
        return "N/D"


def fmt_km(val) -> str:
    try:
        return f"{int(val):,}\u00a0km".replace(",", "\u00a0")
    except Exception:
        return "N/D"


def format_vehicle_card(vehicle: dict) -> str:
    """Retourne une fiche véhicule en HTML à partir d'un dict véhicule."""
    annee        = vehicle.get("year") or vehicle.get("annee") or "N/D"
    marque       = vehicle.get("make") or vehicle.get("marque") or "N/D"
    modele       = vehicle.get("model") or vehicle.get("modele") or "N/D"
    version      = vehicle.get("trim") or ""
    concess      = vehicle.get("dealer_name") or vehicle.get("dealer") or vehicle.get("concessionnaire") or "N/D"
    ville        = vehicle.get("city") or vehicle.get("ville") or "N/D"
    couleur      = vehicle.get("color") or vehicle.get("couleur") or ""
    moteur       = vehicle.get("engine") or vehicle.get("moteur") or "N/D"
    transmission = vehicle.get("transmission") or "N/D"
    traction     = vehicle.get("drivetrain") or vehicle.get("traction") or "N/D"
    carburant    = vehicle.get("fuel_type") or vehicle.get("carburant") or "N/D"
    vin          = vehicle.get("vin") or "N/D"
    url          = vehicle.get("url") or ""

    prix_raw     = vehicle.get("price") or vehicle.get("prix") or 0
    marche_raw   = vehicle.get("avg_market_price") or vehicle.get("market_price") or 0

    try:
        prix_float   = float(prix_raw)
    except Exception:
        prix_float   = 0.0
    try:
        marche_float = float(marche_raw)
    except Exception:
        marche_float = 0.0

    statut       = get_statut_prix(prix_float, marche_float)
    couleur_hex  = get_couleur_hex(couleur)

    # Taxes — utiliser valeurs DB si disponibles, sinon calculer
    tps_db   = vehicle.get("tps")
    tvq_db   = vehicle.get("tvq")
    tot_db   = vehicle.get("total_with_taxes")
    if tps_db and tvq_db and tot_db:
        try:
            taxes = {
                "tps":   f"{float(tps_db):,.2f}\u00a0$".replace(",", "\u00a0"),
                "tvq":   f"{float(tvq_db):,.2f}\u00a0$".replace(",", "\u00a0"),
                "total": f"{float(tot_db):,.2f}\u00a0$".replace(",", "\u00a0"),
            }
        except Exception:
            taxes = calc_taxes(prix_float)
    else:
        taxes = calc_taxes(prix_float)

    prix_str    = fmt_prix(prix_float) if prix_float else "N/D"
    marche_str  = fmt_prix(marche_float) if marche_float else "N/D"
    km_str      = fmt_km(vehicle.get("mileage") or vehicle.get("kilometrage") or 0)
    couleur_str = couleur.title() if couleur else "N/D"
    titre_modele = f"{annee} {marque} {modele}" + (f" {version}" if version else "")

    # Construire le titre avec ou sans lien
    if url:
        titre_html = (
            f'<a href="{url}" target="_blank" rel="noopener" '
            f'style="text-decoration:none;color:inherit;">{titre_modele}</a>'
        )
    else:
        titre_html = titre_modele

    # Toute la carte sur une seule ligne pour éviter que formatText convertisse \n en <br> à l'intérieur du HTML
    card = (
        '<div style="background:#ffffff;border-radius:12px;border:1px solid rgba(0,0,0,0.10);overflow:hidden;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;max-width:560px;margin:8px 0;">'
        '<div style="padding:14px 18px;border-bottom:1px solid rgba(0,0,0,0.08);background:#f7f7f5;">'
        '<p style="font-size:10px;color:#888;margin:0 0 4px;text-transform:uppercase;letter-spacing:0.06em;">V\u00e9hicule d\'occasion</p>'
        f'<p style="font-size:17px;font-weight:600;margin:0;color:#1a1a1a;">{titre_html}</p>'
        f'<p style="font-size:12px;color:#888;margin:3px 0 0;">{concess} &nbsp;\u00b7&nbsp; {ville}</p>'
        '</div>'
        '<div>'
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 18px;border-bottom:1px solid rgba(0,0,0,0.06);">'
        '<span style="font-size:13px;color:#666;">Prix affich\u00e9</span>'
        f'<span style="font-size:14px;font-weight:600;color:#1a1a1a;">{prix_str}</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 18px;border-bottom:1px solid rgba(0,0,0,0.06);">'
        '<span style="font-size:13px;color:#666;">Positionnement march\u00e9</span>'
        f'<span style="font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;'
        f'background:{statut["bg"]};color:{statut["color"]};">'
        f'&#9675; {statut["label"]} (moy. {marche_str})</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 18px;border-bottom:1px solid rgba(0,0,0,0.06);">'
        '<span style="font-size:13px;color:#666;">Kilom\u00e9trage</span>'
        f'<span style="font-size:13px;font-weight:600;color:#1a1a1a;">{km_str}</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 18px;border-bottom:1px solid rgba(0,0,0,0.06);">'
        '<span style="font-size:13px;color:#666;">M\u00e9canique</span>'
        f'<span style="font-size:13px;font-weight:600;color:#1a1a1a;">{moteur} &nbsp;\u00b7&nbsp; {transmission} &nbsp;\u00b7&nbsp; {traction}</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 18px;border-bottom:1px solid rgba(0,0,0,0.06);">'
        '<span style="font-size:13px;color:#666;">Carburant</span>'
        f'<span style="font-size:13px;font-weight:600;color:#1a1a1a;">{carburant}</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 18px;border-bottom:1px solid rgba(0,0,0,0.06);">'
        '<span style="font-size:13px;color:#666;">Couleur</span>'
        f'<span style="font-size:13px;font-weight:600;color:#1a1a1a;display:flex;align-items:center;gap:6px;">'
        f'{couleur_str}'
        f'<span style="display:inline-block;width:10px;height:10px;background:{couleur_hex};border-radius:50%;"></span>'
        '</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 18px;">'
        '<span style="font-size:13px;color:#666;">VIN</span>'
        f'<span style="font-size:11px;color:#888;font-family:\'Courier New\',monospace;letter-spacing:0.03em;">{vin}</span>'
        '</div>'
        '</div>'
        '<div style="border-top:1px solid rgba(0,0,0,0.08);background:#f7f7f5;padding:12px 18px;display:flex;justify-content:space-between;align-items:center;">'
        f'<span style="font-size:12px;color:#888;">TPS {taxes["tps"]} &nbsp;+&nbsp; TVQ {taxes["tvq"]}</span>'
        f'<span style="font-size:16px;font-weight:700;color:#1a1a1a;">Total {taxes["total"]}</span>'
        '</div>'
        '</div>'
    )
    return card


def format_vehicles_html_block(results: list) -> str:
    """Retourne un bloc HTML avec toutes les fiches véhicules, sans marqueurs."""
    if not results:
        return ""
    cards = []
    for r in results:
        prix  = r.get("price", "")
        titre = r.get("title", "")
        if not prix or not titre:
            continue
        cards.append(format_vehicle_card(r))
    return "".join(cards)
