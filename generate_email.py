import argparse
import json
import re
import urllib.parse
from html import escape as esc

def salutation_for(data: dict) -> str:
    """« Bonjour Monsieur X » uniquement si le nom de famille est renseigné explicitement
    (CONTACT_LASTNAME, + CONTACT_CIVILITY si ce n'est pas « Monsieur »). Sinon « Bonjour »."""
    last = (data.get("CONTACT_LASTNAME") or "").strip()
    if not last:
        return "Bonjour,"
    civ = (data.get("CONTACT_CIVILITY") or "Monsieur").strip()
    civ = {"m": "Monsieur", "m.": "Monsieur", "mr": "Monsieur", "mme": "Madame", "mme.": "Madame"}.get(civ.lower(), civ)
    return f"Bonjour {civ} {last},"


def site_domain(data: dict) -> str:
    """Domaine actuel du prospect (SOURCE_SITE_URL) sans « www. », ou chaîne vide."""
    host = urllib.parse.urlparse(data.get("SOURCE_SITE_URL", "")).netloc
    return re.sub(r"^www\.", "", host).strip()


def build_email_content(data: dict):
    """Champs utilisés dans le JSON du prospect :
    BRAND_NAME, CITY, SOURCE_SITE_URL, EMAIL, CONTACT_LASTNAME (+ CONTACT_CIVILITY),
    METIER_PLURIEL (ex. « plombiers-chauffagistes », facultatif)."""
    brand = data.get("BRAND_NAME", "votre entreprise")
    city = data.get("CITY", "")
    domain = site_domain(data)
    metier = (data.get("METIER_PLURIEL") or "").strip()

    subject = f"Projet site web & référencement – {brand}"
    salutation = salutation_for(data)

    cherche = data.get("RECHERCHE") or (f"des artisans {metier}" if metier else "des artisans")
    lieu = data.get("LIEU_PHRASE") or (f" sur {city}" if city else " dans votre secteur")
    site = f"votre site internet ({domain})" if domain else "votre site internet"

    secteur = data.get("SECTEUR", "batiment")
    que = "qu'" if brand[:1].lower() in "aeiouyàâéèêîôhû" else "que "
    if domain:
        p1 = (f"En recherchant {cherche}{lieu}, j'ai consulté {site}. Vos réalisations montrent un vrai "
              "savoir-faire local, mais votre présence en ligne mériterait une vitrine plus moderne : "
              "plus fidèle à la qualité de votre travail et plus simple à utiliser depuis un smartphone.")
    else:  # prospect sans site internet
        p1 = (f"En recherchant {cherche}{lieu}, j'ai remarqué {que}{brand} n'avait pas encore de site internet. "
              "Votre savoir-faire mériterait pourtant une vitrine en ligne claire, visible sur Google et "
              "simple à utiliser depuis un smartphone.")
    if secteur in ("gastro", "beaute"):
        cible = "commerçants" if secteur == "gastro" else "professionnels de la beauté"
        p2 = (f"Pour les {cible} avec lesquels j'échange, la prise de réservations par téléphone est souvent "
              "chronophage, en plein service. Afin de vous faire gagner du temps, j'intègre à mes réalisations "
              "une réservation en ligne : le client choisit sa date, son horaire et ses envies, et vous recevez "
              "une demande claire, sans allers-retours inutiles.")
    else:
        cible = "professionnels du bâtiment" if secteur in ("batiment", "bois") else "artisans"
        p2 = (f"Pour les {cible} avec lesquels j'échange, le traitement des demandes est souvent "
              "chronophage le soir après les chantiers. Afin de vous faire gagner du temps, j'intègre à mes "
              "réalisations un devis interactif : le client est guidé par étapes (type de prestation, détails du "
              "besoin, photos, coordonnées) et vous recevez une fiche récapitulative claire, prête à être chiffrée, "
              "sans allers-retours inutiles.")
    p3 = (f"Pour vous donner un aperçu concret, j'ai pris l'initiative de concevoir une première ébauche "
          f"visuelle sur mesure pour {brand} (adaptée sur ordinateur et sur mobile). Il ne s'agit pas d'une "
          "version définitive : tout reste modifiable selon vos envies (textes, photos, couleurs, pages), et de "
          "nombreuses fonctionnalités peuvent être ajoutées selon vos besoins.")
    p4 = "Vous la trouverez directement en pièce jointe de ce message."
    p5 = ("Si cette approche vous parle, n'hésitez pas à me faire part de votre avis sur la maquette, "
          "par mail ou par téléphone, sans aucun engagement.")
    paras = [p1, p2, p3, p4, p5]

    plain_body = f"""{salutation}

""" + "\n\n".join(paras) + """

Bien cordialement,

[Votre Prénom] [Votre Nom]
Développeur Web & Logiciel
[Votre Téléphone]"""

    html_paras = "\n    ".join(
        f"<p>{esc(t)}</p>" if t is not p4 else f"<p><strong>{esc(t)}</strong></p>" for t in paras)
    html_body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: Helvetica, Arial, sans-serif; line-height: 1.65; color: #1e293b; background-color: #ffffff; margin: 0; padding: 15px 0; }}
  .container {{ max-width: 600px; margin: 0; }}
  p {{ margin: 0 0 16px; font-size: 16px; }}
</style>
</head>
<body>
  <div class="container">
    <p>{esc(salutation)}</p>
    {html_paras}
    <p>Bien cordialement,</p>
    <div class="signature">
      <strong>[Votre Prénom] [Votre Nom]</strong><br>
      Développeur Web &amp; Logiciel<br>
      <span>[Votre Téléphone]</span>
    </div>
  </div>
</body>
</html>"""

    mailto_url = f"mailto:{data.get('EMAIL', '')}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(plain_body)}"

    return subject, plain_body, html_body, mailto_url

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="Fichier JSON du prospect")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        data = json.load(f)

    subject, plain_body, html_body, mailto_url = build_email_content(data)

    # Sauvegarde d'un fichier de prévisualisation HTML
    with open("apercu_email.html", "w", encoding="utf-8") as f:
        f.write(html_body)

    print("=" * 60)
    print(f"OBJET : {subject}")
    print("=" * 60)
    print(plain_body)
    print("=" * 60)
    print("\n[OK] Fichier 'apercu_email.html' généré pour voir le rendu visuel.")
    print(f"[LIEN RAPIDE] Tu peux cliquer ou copier ce lien pour ouvrir ton client mail :\n{mailto_url}")

if __name__ == "__main__":
    main()