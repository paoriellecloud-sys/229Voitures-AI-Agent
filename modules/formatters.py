"""Formatters pour les fiches véhicules HTML."""
import re


def build_fo_url(v: dict) -> str:
    """Construit l'URL Force Occasion au format /occasion/Marque-Modele-Annee-id{id}.html"""
    stored_url = v.get("url") or v.get("listing_url") or v.get("force_occasion_url") or ""
    # Déjà au bon format /occasion/
    if stored_url and "/occasion/" in stored_url:
        return stored_url
    # Extraire l'ID depuis l'URL /fiche/ stockée ou depuis vehicle_id
    fo_id = v.get("vehicle_id") or v.get("fo_id") or ""
    if not fo_id and stored_url:
        m = re.search(r"/fiche/(\d+)", stored_url)
        if m:
            fo_id = m.group(1)
    if not fo_id:
        return stored_url or "https://www.forceoccasion.ca"
    marque = (v.get("make") or v.get("marque") or "").strip().replace(" ", "-")
    modele = (v.get("model") or v.get("modele") or "").strip().replace("-", "").replace(" ", "_")
    annee  = str(v.get("year") or v.get("annee") or "").strip()
    if marque and modele and annee:
        return f"https://www.forceoccasion.ca/occasion/{marque}-{modele}-{annee}-id{fo_id}.html"
    return f"https://www.forceoccasion.ca/occasion/vehicule-id{fo_id}.html"

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


def format_vehicle_card(v: dict) -> str:
    """Retourne une fiche véhicule HTML thème sombre à partir d'un dict véhicule."""
    annee        = v.get("year") or v.get("annee") or ""
    marque       = v.get("make") or v.get("marque") or ""
    modele       = v.get("model") or v.get("modele") or ""
    version      = v.get("trim") or ""
    concess      = v.get("dealer_name") or v.get("dealer") or v.get("concessionnaire") or "N/D"
    ville        = v.get("city") or v.get("ville") or "Québec"
    couleur      = v.get("color") or v.get("couleur") or ""
    moteur_raw   = v.get("engine") or v.get("moteur") or ""
    moteur       = moteur_raw.strip().strip(".").strip() or "N/D"
    transmission = v.get("transmission") or "N/D"
    traction     = v.get("drivetrain") or v.get("traction") or "N/D"
    carburant    = v.get("fuel_type") or v.get("carburant") or "N/D"
    stock_raw    = v.get("stock_number") or v.get("stock_no") or v.get("no_stock") or ""
    stock_number = stock_raw.replace("-neuf", "").replace("-used", "").replace("-occ", "").strip()
    vin          = v.get("vin") or "N/D"
    url_fiche    = build_fo_url(v)

    try:
        prix_float   = float(v.get("price") or v.get("prix") or 0)
    except Exception:
        prix_float   = 0.0
    try:
        marche_float = float(v.get("avg_market_price") or v.get("market_price") or v.get("marche_moyen") or 0)
    except Exception:
        marche_float = 0.0

    statut      = get_statut_prix(prix_float, marche_float)
    couleur_hex = get_couleur_hex(couleur)

    # Taxes — valeurs DB en priorité, sinon calculer
    tps_db = v.get("tps")
    tvq_db = v.get("tvq")
    tot_db = v.get("total_with_taxes")
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

    mecanique   = f"{moteur} \u00a0\u00b7\u00a0 {transmission}" if moteur and moteur != "N/D" else transmission
    prix_str    = fmt_prix(prix_float) if prix_float else "N/D"
    marche_str  = fmt_prix(marche_float) if marche_float else "N/D"
    km_str      = fmt_km(v.get("mileage") or v.get("kilometrage") or 0)
    couleur_str = couleur.title() if couleur else "N/D"
    titre       = f"{annee} {marque} {modele}".strip() + (f" {version}" if version else "")

    # Badge statut marché — couleurs thème sombre
    badge_styles = {
        "Bon prix":             "background:rgba(99,153,34,0.18);color:#97C459;border:1px solid rgba(99,153,34,0.3);",
        "Prix dans la moyenne": "background:rgba(186,117,23,0.18);color:#FAC775;border:1px solid rgba(186,117,23,0.3);",
        "Prix \u00e9lev\u00e9": "background:rgba(226,75,74,0.15);color:#F09595;border:1px solid rgba(226,75,74,0.3);",
        "Prix non compar\u00e9":"background:rgba(136,135,128,0.18);color:#888780;border:1px solid rgba(136,135,128,0.3);",
    }
    badge_style = badge_styles.get(statut["label"], badge_styles["Prix non compar\u00e9"])

    # Carte sur une seule ligne — évite que formatText convertisse \n en <br> dans le HTML
    return (
        '<div style="border-radius:10px;border:1px solid rgba(255,255,255,0.10);overflow:hidden;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;max-width:560px;margin:8px 0;background:rgba(255,255,255,0.04);">'
        # En-tête
        '<div style="padding:14px 18px;border-bottom:1px solid rgba(255,255,255,0.08);">'
        '<p style="font-size:10px;color:#666;margin:0 0 6px;text-transform:uppercase;letter-spacing:0.06em;">V\u00e9hicule d\'occasion</p>'
        '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">'
        f'<p style="font-size:18px;font-weight:600;margin:0;color:#f0f0f0;">{titre}</p>'
        f'<a href="{url_fiche}" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:600;color:#FAC775;background:rgba(250,199,117,0.12);border:1px solid rgba(250,199,117,0.25);padding:4px 10px;border-radius:20px;text-decoration:none;white-space:nowrap;">&#9733; Force Occasion &#8594;</a>'
        '</div>'
        f'<p style="font-size:12px;color:#666;margin:4px 0 0;">{concess} &nbsp;\u00b7&nbsp; {ville}</p>'
        '</div>'
        # Lignes de données
        '<div>'
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">'
        '<span style="font-size:13px;color:#888;">Prix affich\u00e9</span>'
        f'<span style="font-size:14px;font-weight:600;color:#f0f0f0;">{prix_str}</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">'
        '<span style="font-size:13px;color:#888;">Positionnement march\u00e9</span>'
        f'<span style="font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;{badge_style}">&#9675; {statut["label"]} (moy. {marche_str})</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">'
        '<span style="font-size:13px;color:#888;">Kilom\u00e9trage</span>'
        f'<span style="font-size:13px;font-weight:600;color:#f0f0f0;">{km_str}</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">'
        '<span style="font-size:13px;color:#888;">M\u00e9canique</span>'
        f'<span style="font-size:13px;font-weight:600;color:#f0f0f0;">{mecanique}</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">'
        '<span style="font-size:13px;color:#888;">Traction</span>'
        f'<span style="font-size:13px;font-weight:600;color:#f0f0f0;">{traction}</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">'
        '<span style="font-size:13px;color:#888;">Carburant</span>'
        f'<span style="font-size:13px;font-weight:600;color:#f0f0f0;">{carburant}</span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">'
        '<span style="font-size:13px;color:#888;">Couleur</span>'
        f'<span style="font-size:13px;font-weight:600;color:#f0f0f0;display:flex;align-items:center;gap:6px;">{couleur_str}'
        f'<span style="display:inline-block;width:10px;height:10px;background:{couleur_hex};border-radius:50%;border:1px solid rgba(255,255,255,0.15);"></span>'
        '</span>'
        '</div>'
        + (
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">'
        '<span style="font-size:13px;color:#888;">Num. stock</span>'
        f'<span style="font-size:12px;font-weight:500;color:#c0c0c0;font-family:\'Courier New\',monospace;letter-spacing:0.05em;">{stock_number}</span>'
        '</div>'
        if stock_number else ''
        ) +
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 18px;">'
        '<span style="font-size:13px;color:#888;">VIN</span>'
        f'<span style="font-size:12px;font-weight:500;color:#c0c0c0;font-family:\'Courier New\',monospace;letter-spacing:0.05em;">{vin}</span>'
        '</div>'
        '</div>'
        # Pied — taxes
        '<div style="border-top:1px solid rgba(255,255,255,0.08);padding:12px 18px;display:flex;justify-content:space-between;align-items:center;background:rgba(255,255,255,0.03);">'
        f'<span style="font-size:12px;color:#666;">TPS {taxes["tps"]} &nbsp;+&nbsp; TVQ {taxes["tvq"]}</span>'
        f'<span style="font-size:16px;font-weight:700;color:#f0f0f0;">Total {taxes["total"]}</span>'
        '</div>'
        '</div>'
    )


def generate_vin_report(data: dict) -> str:
    """Génère la fiche HTML du rapport VIN aux couleurs 229Voitures."""
    vin          = data.get("vin", "N/D")
    annee        = data.get("annee", "")
    marque       = data.get("make") or data.get("marque", "")
    modele       = data.get("model") or data.get("modele", "")
    type_v       = data.get("type_vehicule", "N/D")
    moteur       = data.get("moteur") or data.get("engine", "N/D")
    transmission = data.get("transmission", "N/D")
    traction     = data.get("traction") or data.get("drivetrain", "N/D")
    assemble     = data.get("assemble", "N/D")
    usage        = data.get("usage", "N/D")
    rappels      = data.get("rappels", "Aucun rappel actif")
    rappels_ok   = data.get("rappels_ok", True)
    plaintes     = data.get("plaintes", "Peu de plaintes enregistr\u00e9es")
    plaintes_ok  = data.get("plaintes_ok", True)
    points       = data.get("points_surveiller", [])
    prix_min     = data.get("prix_min", "N/D")
    prix_max     = data.get("prix_max", "N/D")
    prix_moyen   = data.get("prix_moyen", "N/D")
    sources      = data.get("sources_prix", "AutoTrader \u00b7 CarGurus")
    rec_titre    = data.get("recommandation_titre", "Inspecter avant achat")
    rec_texte    = data.get("recommandation_texte", "Une inspection pr\u00e9-achat est recommand\u00e9e.")
    rec_niveau   = data.get("recommandation_niveau", "attention")

    rec_colors = {
        "ok":       ("rgba(99,153,34,0.12)",  "rgba(99,153,34,0.30)",  "#97C459", "&#9989;"),
        "attention":("rgba(186,117,23,0.12)", "rgba(186,117,23,0.30)", "#FAC775", "&#9888;"),
        "danger":   ("rgba(226,75,74,0.12)",  "rgba(226,75,74,0.30)",  "#F09595", "&#128721;"),
    }
    rec_bg, rec_border, rec_color, rec_icon = rec_colors.get(rec_niveau, rec_colors["attention"])

    if rappels_ok:
        rappels_html = f'<div style="display:flex;align-items:center;gap:8px;background:rgba(99,153,34,0.15);border:1px solid rgba(99,153,34,0.30);border-radius:8px;padding:10px 12px;"><span style="font-size:15px;">&#9989;</span><span style="font-size:13px;color:#97C459;font-weight:500;">{rappels}</span></div>'
    else:
        rappels_html = f'<div style="display:flex;align-items:center;gap:8px;background:rgba(226,75,74,0.12);border:1px solid rgba(226,75,74,0.30);border-radius:8px;padding:10px 12px;"><span style="font-size:15px;">&#128721;</span><span style="font-size:13px;color:#F09595;font-weight:500;">{rappels}</span></div>'

    if plaintes_ok:
        plaintes_html = f'<div style="display:flex;align-items:center;gap:8px;background:rgba(99,153,34,0.15);border:1px solid rgba(99,153,34,0.30);border-radius:8px;padding:10px 12px;"><span style="font-size:15px;">&#9989;</span><span style="font-size:13px;color:#97C459;font-weight:500;">{plaintes}</span></div>'
    else:
        plaintes_html = f'<div style="display:flex;align-items:center;gap:8px;background:rgba(226,75,74,0.12);border:1px solid rgba(226,75,74,0.30);border-radius:8px;padding:10px 12px;"><span style="font-size:15px;">&#128721;</span><span style="font-size:13px;color:#F09595;font-weight:500;">{plaintes}</span></div>'

    if points:
        points_items = "".join([
            f'<div style="display:flex;align-items:flex-start;gap:8px;padding:8px 12px;background:rgba(186,117,23,0.12);border:1px solid rgba(186,117,23,0.25);border-radius:8px;"><span style="font-size:13px;color:#FAC775;flex-shrink:0;margin-top:1px;">&#9888;</span><span style="font-size:12px;color:#c0c0c0;line-height:1.5;">{p}</span></div>'
            for p in points
        ])
        points_html = f'<div style="display:flex;flex-direction:column;gap:6px;">{points_items}</div>'
    else:
        points_html = '<div style="display:flex;align-items:center;gap:8px;background:rgba(99,153,34,0.15);border:1px solid rgba(99,153,34,0.30);border-radius:8px;padding:10px 12px;"><span style="font-size:15px;">&#9989;</span><span style="font-size:13px;color:#97C459;font-weight:500;">Aucun point critique identifi\u00e9</span></div>'

    # Carte sur une seule ligne — évite que formatText convertisse \n en <br> dans le HTML
    return (
        '<div style="border-radius:10px;border:1px solid rgba(255,255,255,0.10);overflow:hidden;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;max-width:560px;margin:8px 0;background:rgba(255,255,255,0.04);">'
        '<div style="padding:14px 18px;border-bottom:1px solid rgba(255,255,255,0.08);">'
        '<p style="font-size:10px;color:#666;margin:0 0 4px;text-transform:uppercase;letter-spacing:0.06em;">Rapport VIN</p>'
        f'<p style="font-size:17px;font-weight:600;margin:0;color:#f0f0f0;">{annee} {marque} {modele}</p>'
        f'<p style="font-size:12px;color:#666;margin:3px 0 0;font-family:\'Courier New\',monospace;letter-spacing:0.05em;">{vin}</p>'
        '</div>'
        # Véhicule
        '<div style="padding:12px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">'
        '<p style="font-size:10px;color:#FAC775;margin:0 0 8px;text-transform:uppercase;letter-spacing:0.06em;">&#128663; V\u00e9hicule</p>'
        '<div style="display:flex;flex-direction:column;gap:6px;">'
        f'<div style="display:flex;justify-content:space-between;"><span style="font-size:13px;color:#888;">Type</span><span style="font-size:13px;font-weight:500;color:#f0f0f0;">{type_v}</span></div>'
        f'<div style="display:flex;justify-content:space-between;"><span style="font-size:13px;color:#888;">Moteur</span><span style="font-size:13px;font-weight:500;color:#f0f0f0;">{moteur}</span></div>'
        f'<div style="display:flex;justify-content:space-between;"><span style="font-size:13px;color:#888;">Transmission</span><span style="font-size:13px;font-weight:500;color:#f0f0f0;">{transmission}</span></div>'
        f'<div style="display:flex;justify-content:space-between;"><span style="font-size:13px;color:#888;">Traction</span><span style="font-size:13px;font-weight:500;color:#f0f0f0;">{traction}</span></div>'
        f'<div style="display:flex;justify-content:space-between;"><span style="font-size:13px;color:#888;">Assembl\u00e9</span><span style="font-size:13px;font-weight:500;color:#f0f0f0;">{assemble} \u00b7 {usage}</span></div>'
        '</div></div>'
        # Rappels
        '<div style="padding:12px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">'
        '<p style="font-size:10px;color:#FAC775;margin:0 0 8px;text-transform:uppercase;letter-spacing:0.06em;">&#9888; Rappels de s\u00e9curit\u00e9</p>'
        f'{rappels_html}'
        '</div>'
        # Plaintes
        '<div style="padding:12px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">'
        '<p style="font-size:10px;color:#FAC775;margin:0 0 8px;text-transform:uppercase;letter-spacing:0.06em;">&#128202; Plaintes propri\u00e9taires</p>'
        f'{plaintes_html}'
        '</div>'
        # Points à surveiller
        '<div style="padding:12px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">'
        '<p style="font-size:10px;color:#FAC775;margin:0 0 8px;text-transform:uppercase;letter-spacing:0.06em;">&#128295; Points \u00e0 surveiller</p>'
        f'{points_html}'
        '</div>'
        # Valeur marché
        '<div style="padding:12px 18px;border-bottom:1px solid rgba(255,255,255,0.06);">'
        '<p style="font-size:10px;color:#FAC775;margin:0 0 8px;text-transform:uppercase;letter-spacing:0.06em;">&#128181; Valeur march\u00e9 Canada</p>'
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">'
        '<div style="background:rgba(255,255,255,0.05);border-radius:8px;padding:10px 12px;">'
        '<p style="font-size:11px;color:#888;margin:0 0 3px;">Fourchette</p>'
        f'<p style="font-size:13px;font-weight:600;color:#f0f0f0;margin:0;">{prix_min} \u2014 {prix_max}</p>'
        '</div>'
        '<div style="background:rgba(255,255,255,0.05);border-radius:8px;padding:10px 12px;">'
        '<p style="font-size:11px;color:#888;margin:0 0 3px;">Prix moyen</p>'
        f'<p style="font-size:15px;font-weight:700;color:#FAC775;margin:0;">~ {prix_moyen}</p>'
        '</div>'
        '</div>'
        f'<p style="font-size:11px;color:#555;margin:0;">Sources : {sources}</p>'
        '</div>'
        # Recommandation
        '<div style="padding:12px 18px;border-bottom:1px solid rgba(255,255,255,0.08);">'
        '<p style="font-size:10px;color:#FAC775;margin:0 0 8px;text-transform:uppercase;letter-spacing:0.06em;">&#127919; Recommandation</p>'
        f'<div style="display:flex;align-items:flex-start;gap:10px;background:{rec_bg};border:1px solid {rec_border};border-radius:8px;padding:12px 14px;">'
        f'<span style="font-size:18px;flex-shrink:0;">{rec_icon}</span>'
        '<div>'
        f'<p style="font-size:13px;font-weight:600;color:{rec_color};margin:0 0 3px;">{rec_titre}</p>'
        f'<p style="font-size:12px;color:#c0c0c0;margin:0;line-height:1.5;">{rec_texte}</p>'
        '</div>'
        '</div>'
        '</div>'
        # Footer
        '<div style="padding:10px 18px;background:rgba(0,0,0,0.15);">'
        '<p style="font-size:11px;color:#555;margin:0;text-align:center;">&#9888; Donn\u00e9es \u00e0 titre informatif \u00b7 229Voitures n\'est pas un conseiller financier</p>'
        '</div>'
        '</div>'
    )


def generate_rdv_form(vehicle: dict) -> str:
    """Retourne un formulaire HTML de demande de rendez-vous pré-rempli avec les infos du véhicule."""
    annee  = str(vehicle.get("year") or vehicle.get("annee") or "").strip()
    marque = (vehicle.get("make") or vehicle.get("marque") or "").strip()
    modele = (vehicle.get("model") or vehicle.get("modele") or "").strip()
    dealer = (vehicle.get("dealer_name") or vehicle.get("dealer") or vehicle.get("concessionnaire") or "N/D").strip()
    ville  = (vehicle.get("city") or vehicle.get("ville") or "Québec").strip()
    veh    = f"{annee} {marque} {modele}".strip()

    return (
        '<div style="border-radius:10px;border:1px solid rgba(255,255,255,0.10);overflow:hidden;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;max-width:520px;margin:8px 0;background:rgba(255,255,255,0.04);">'
        '<div style="padding:14px 18px;border-bottom:1px solid rgba(255,255,255,0.08);">'
        '<p style="font-size:10px;color:#666;margin:0 0 4px;text-transform:uppercase;letter-spacing:0.06em;">Demande de rendez-vous</p>'
        f'<p style="font-size:16px;font-weight:600;margin:0;color:#f0f0f0;">{veh}</p>'
        f'<p style="font-size:12px;color:#666;margin:3px 0 0;">{dealer} \u00b7 {ville}</p>'
        '</div>'
        '<div style="padding:16px 18px;display:flex;flex-direction:column;gap:12px;">'
        '<div><label style="font-size:11px;color:#888;display:block;margin-bottom:5px;text-transform:uppercase;letter-spacing:0.05em;">Pr\u00e9nom et nom *</label>'
        '<input type="text" placeholder="Votre nom complet" style="width:100%;box-sizing:border-box;background:rgba(255,255,255,0.05);border:1px solid rgba(250,199,117,0.20);border-radius:8px;padding:10px 12px;color:#f0f0f0;font-size:13px;outline:none;" id="rdv_nom" onfocus="this.style.borderColor=\'rgba(250,199,117,0.6)\'" onblur="this.style.borderColor=\'rgba(250,199,117,0.20)\'"></div>'
        '<div><label style="font-size:11px;color:#888;display:block;margin-bottom:5px;text-transform:uppercase;letter-spacing:0.05em;">T\u00e9l\u00e9phone *</label>'
        '<input type="tel" placeholder="Votre num\u00e9ro de t\u00e9l\u00e9phone" style="width:100%;box-sizing:border-box;background:rgba(255,255,255,0.05);border:1px solid rgba(250,199,117,0.20);border-radius:8px;padding:10px 12px;color:#f0f0f0;font-size:13px;outline:none;" id="rdv_tel" onfocus="this.style.borderColor=\'rgba(250,199,117,0.6)\'" onblur="this.style.borderColor=\'rgba(250,199,117,0.20)\'"></div>'
        '<div><label style="font-size:11px;color:#888;display:block;margin-bottom:5px;text-transform:uppercase;letter-spacing:0.05em;">Courriel *</label>'
        '<input type="email" placeholder="Votre adresse courriel" style="width:100%;box-sizing:border-box;background:rgba(255,255,255,0.05);border:1px solid rgba(250,199,117,0.20);border-radius:8px;padding:10px 12px;color:#f0f0f0;font-size:13px;outline:none;" id="rdv_email" onfocus="this.style.borderColor=\'rgba(250,199,117,0.6)\'" onblur="this.style.borderColor=\'rgba(250,199,117,0.20)\'"></div>'
        '<div><label style="font-size:11px;color:#888;display:block;margin-bottom:5px;text-transform:uppercase;letter-spacing:0.05em;">Message (optionnel)</label>'
        '<textarea placeholder="Pr\u00e9cisez vos disponibilit\u00e9s ou toute autre question..." rows="3" style="width:100%;box-sizing:border-box;background:rgba(255,255,255,0.05);border:1px solid rgba(250,199,117,0.20);border-radius:8px;padding:10px 12px;color:#f0f0f0;font-size:13px;outline:none;resize:none;font-family:inherit;" id="rdv_msg" onfocus="this.style.borderColor=\'rgba(250,199,117,0.6)\'" onblur="this.style.borderColor=\'rgba(250,199,117,0.20)\'"></textarea></div>'
        f'<button onclick="const nom=document.getElementById(\'rdv_nom\').value.trim();const tel=document.getElementById(\'rdv_tel\').value.trim();const email=document.getElementById(\'rdv_email\').value.trim();const msg=document.getElementById(\'rdv_msg\').value.trim();if(!nom||!tel||!email){{alert(\'Veuillez remplir les champs obligatoires (*)\');return;}}sendSuggestion(\'DEMANDE_RDV | V\u00e9hicule: {veh} | Concessionnaire: {dealer} | Nom: \'+nom+\' | T\u00e9l: \'+tel+\' | Courriel: \'+email+(msg?\' | Message: \'+msg:\'\'));" style="background:#FAC775;color:#1a1a1a;border:none;border-radius:8px;padding:12px 18px;font-size:13px;font-weight:700;cursor:pointer;width:100%;" onmouseover="this.style.background=\'#f0b84d\'" onmouseout="this.style.background=\'#FAC775\'">Envoyer ma demande &#8599;</button>'
        '<p style="font-size:11px;color:#555;margin:0;text-align:center;">Le concessionnaire vous contactera dans les 24-48h.</p>'
        '</div>'
        '</div>'
    )


def format_vehicles_html_block(results: list) -> str:
    """Retourne un bloc HTML avec les 3 premières fiches véhicules numérotées."""
    if not results:
        return ""
    cards = []
    n = 0
    for r in results:
        if n >= 3:
            break
        prix  = r.get("price", "")
        titre = r.get("title", "")
        if not prix or not titre:
            continue
        n += 1
        label = (
            '<div style="font-size:11px;font-weight:700;color:#888;text-transform:uppercase;'
            'letter-spacing:0.08em;margin:16px 0 4px;">'
            f'Proposition {n}'
            '</div>'
        )
        cards.append(label + format_vehicle_card(r))
    return "".join(cards)
