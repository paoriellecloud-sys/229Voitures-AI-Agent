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


def format_vehicle_card(v: dict) -> str:
    """Retourne une fiche véhicule HTML thème sombre à partir d'un dict véhicule."""
    annee        = v.get("year") or v.get("annee") or ""
    marque       = v.get("make") or v.get("marque") or ""
    modele       = v.get("model") or v.get("modele") or ""
    version      = v.get("trim") or ""
    concess      = v.get("dealer_name") or v.get("dealer") or v.get("concessionnaire") or "N/D"
    ville        = v.get("city") or v.get("ville") or "Québec"
    couleur      = v.get("color") or v.get("couleur") or ""
    moteur       = v.get("engine") or v.get("moteur") or "N/D"
    transmission = v.get("transmission") or "N/D"
    traction     = v.get("drivetrain") or v.get("traction") or "N/D"
    carburant    = v.get("fuel_type") or v.get("carburant") or "N/D"
    stock_number = v.get("stock_number") or v.get("no_stock") or ""
    vin          = v.get("vin") or "N/D"
    # URL directe : priorité vehicle_id Force Occasion, sinon url stockée
    vehicle_id   = v.get("vehicle_id") or ""
    if vehicle_id:
        url_fiche = f"https://www.forceoccasion.com/used-car/{vehicle_id}/"
    else:
        url_fiche = v.get("url") or v.get("listing_url") or v.get("force_occasion_url") or "https://www.forceoccasion.com"

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
        f'<span style="font-size:13px;font-weight:600;color:#f0f0f0;">{moteur} &nbsp;\u00b7&nbsp; {transmission}</span>'
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
        '<span style="font-size:13px;color:#888;">No stock</span>'
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
