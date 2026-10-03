import argparse
import asyncio
import colorsys
import html as htmllib
import json
import os
import re
import unicodedata
from playwright.async_api import async_playwright

# ---------------------------------------------------------------------------
# Thèmes : choisis automatiquement selon le métier détecté dans prospect.json.
# Force un thème avec "THEME": "bois" (ou un dict de couleurs) dans prospect.json.
# "hot" = couleur des boutons d'action (par défaut = accent).
# Si un LOGO est fourni, l'accent est automatiquement tiré des couleurs du logo.
# ---------------------------------------------------------------------------
THEMES = {
    "bois": dict(
        keywords=["menuiser", "bois", "ebenist", "agencement", "charpent", "parquet"],
        bg="#f6f0e6", surface="#fffaf1", text="#2b1d12", muted="#7a6552",
        accent="#8a5a2b", accent_text="#ffffff", soft="#eadcc6", border="#dccbb0",
        heading_font="Playfair Display", body_font="Lato",
    ),
    "batiment": dict(
        keywords=["plomb", "chauff", "electri", "batiment", "maconn", "renovation", "travaux", "toiture", "couvreur", "depann", "serrur", "volet", "deboucha", "clim", "vitr", "peintre", "carrel", "isolation", "facade", "piscin"],
        bg="#f1f5f9", surface="#ffffff", text="#0f2438", muted="#5b6b7c",
        accent="#e8730c", accent_text="#ffffff", soft="#dbe7f3", border="#cbd8e6",
        heading_font="Montserrat", body_font="Inter",
    ),
    "nature": dict(
        keywords=["paysag", "jardin", "espace vert", "bio", "horticul", "pepinier"],
        bg="#f1f6ee", surface="#ffffff", text="#17301f", muted="#5d7364",
        accent="#2f7d4f", accent_text="#ffffff", soft="#dcebd6", border="#c9ddc3",
        heading_font="Merriweather", body_font="Nunito Sans",
    ),
    "gastro": dict(
        keywords=["restaur", "boulanger", "patiss", "traiteur", "cuisine", "brasserie", "cafe", "bistro", "tapas", "bar ", "pizz", "glacier", "kebab", "burger", "epicerie", "fromag", "boucher", "traiteur"],
        bg="#f8f3ec", surface="#fffdfa", text="#2b1f1a", muted="#7d6459",
        accent="#e0603a", accent_text="#ffffff", soft="#f2ddcf", border="#e7cfc0",
        heading_font="Playfair Display", body_font="Plus Jakarta Sans",
    ),
    "beaute": dict(
        keywords=["coiff", "beaute", "esthetique", "spa", "bien-etre", "massage", "institut", "barbier", "ongle", "tatou", "estheti", "massage"],
        bg="#fbf1f3", surface="#ffffff", text="#33202a", muted="#85697a",
        accent="#b8567a", accent_text="#ffffff", soft="#f4dbe4", border="#ecc8d5",
        heading_font="DM Serif Display", body_font="DM Sans",
    ),
    "auto": dict(
        keywords=["garage", "automobile", "mecanique", "carrosserie", "moto", "pneu", "controle technique"],
        bg="#eef0f2", surface="#ffffff", text="#14181d", muted="#5f6873",
        accent="#d62828", accent_text="#ffffff", soft="#dfe3e8", border="#cfd4da",
        heading_font="Oswald", body_font="Roboto",
    ),
    "default": dict(
        keywords=[],
        bg="#f5f6fa", surface="#ffffff", text="#1b1f3b", muted="#646a8a",
        accent="#3f4bd8", accent_text="#ffffff", soft="#e1e4fa", border="#d3d7ee",
        heading_font="Poppins", body_font="Inter",
    ),
}

# ---------------------------------------------------------------------------
# Contenu par métier (surchargeable via "SITE": {...} dans prospect.json).
# {brand} et {city} sont remplacés automatiquement.
# ---------------------------------------------------------------------------
PROFILES = {
    "batiment": dict(
        nav=["Accueil", "Réalisations", "Savoir-faire", "Tarifs & devis"],
        cta="Devis en ligne", status="Devis en ligne",
        stats=[],
        p2=dict(eyebrow="Nos chantiers", title="Des réalisations qui parlent d'elles-mêmes",
                sub="Rénovation, dépannage, installation : un aperçu des chantiers menés autour de {city}.",
                add="Demander un devis", foot="Devis gratuit", link="Voir le chantier",
                tags=[("wrench", "Dépannage"), ("thermometer", "Installation"), ("home", "Rénovation"), ("shield", "Qualité")],
                metas=["Intervention rapide", "Installation soignée", "Rénovation", "Travail soigné"],
                extra=("Installation propre, finitions soignées", "Un chantier suivi de A à Z, nettoyé et expliqué avant votre signature.")),
        p3=dict(eyebrow="Savoir-faire", title="Un artisan, tous vos besoins",
                sub="Un interlocuteur unique du diagnostic à la mise en service.",
                cards=[("shield", "Un interlocuteur unique", "Du diagnostic à la remise en service, un seul contact pour votre projet.", "SIMPLE ET DIRECT"),
                       ("clock", "Une demande claire", "Vous décrivez votre besoin, on vous rappelle et l'intervention est planifiée.", "SUIVI DE DEMANDE")],
                quote="« Intervention rapide, travail soigné et un devis respecté au centime. Je recommande sans hésiter. »",
                who="Claire M.", role="Cliente à {city}", caption="Le sérieux d'un artisan local"),
        p4=dict(eyebrow="Prestations & devis", title="Tarifs clairs, zéro surprise",
                sub="Un devis détaillé et gratuit avant chaque intervention.",
                tabs=["Plomberie", "Chauffage", "Salle de bain", "Urgences"],
                head=("Nos prestations", "Devis"),
                items=[("Diagnostic & devis", "SUR DEMANDE", "Analyse de votre besoin et devis détaillé avant intervention.", "Sur devis"),
                       ("Dépannage", "URGENCES", "Une panne, une fuite ? Décrivez le problème, on vous rappelle.", "Rapide"),
                       ("Installation & remplacement", "SOIGNÉ", "Pose et mise en service de votre nouvelle installation.", "Sur devis"),
                       ("Rénovation clé en main", "SUR-MESURE", "Un seul interlocuteur pour l'ensemble de votre projet.", "Sur devis")],
                foot_l="* Devis détaillé avant intervention", foot_r="Réponse rapide", cta="Demander un devis"),
        config=dict(eyebrow="Devis en ligne", title="Décrivez votre besoin, on s'occupe du reste",
                    sub="Trois étapes, environ deux minutes : vous recevez une demande claire, prête à être chiffrée.",
                    steps=["Type de besoin", "Détails", "Coordonnées"],
                    q="Quel est le type d'intervention ?", qsub="Choisissez la prestation qui correspond le mieux à votre besoin.",
                    opts=[("droplet", "Plomberie"), ("bolt", "Électricité"), ("thermometer", "Chauffage"),
                          ("home", "Rénovation"), ("wrench", "Dépannage"), ("sparkle", "Autre demande")],
                    sel=0, ticket_title="Fiche de pré-devis",
                    ticket=[("Type de bien", "Appartement"), ("Prestation", "Plomberie"), ("Urgence", "Cette semaine"),
                            ("Photos jointes", "2 photos"), ("Contact", "Rappel par téléphone")],
                    badge="Réponse rapide", cta="Envoyer ma demande", prev="Retour", next="Continuer"),
    ),
    "bois": dict(
        nav=["Accueil", "Créations", "Savoir-faire", "L'atelier"],
        cta="Projet sur mesure", status="Atelier ouvert",
        stats=[("15+", "ans de métier"), ("100%", "sur mesure"), ("FR", "bois français"), ("4.9★", "avis clients")],
        p2=dict(eyebrow="Créations", title="Le bois, façonné pour vous", sub="Cuisines, dressings, escaliers, meubles : quelques pièces sorties de l'atelier.",
                add="Parler de mon projet", foot="Pièce unique", link="Découvrir",
                tags=[("hammer", "Agencement"), ("leaf", "Bois massif"), ("ruler", "Sur mesure"), ("heart", "Fait main")],
                metas=["Pièce d'atelier", "Essence sélectionnée", "Conçu à vos mesures", "Finition à la main"],
                extra=("Chaque détail compte", "Assemblages, chants, finitions : le geste de l'artisan se voit.")),
        p3=dict(eyebrow="Savoir-faire", title="L'atelier, du croquis à la pose", sub="Conception, fabrication et installation par la même équipe.",
                cards=[("ruler", "Conception sur mesure", "Relevé, plans 3D et choix des essences avec vous.", "ÉTAPE 01"),
                       ("hammer", "Fabrication en atelier", "Usinage, assemblage et finition dans nos murs.", "ÉTAPE 02")],
                quote="« Une cuisine exactement comme on l'imaginait, posée au millimètre. Un vrai travail d'artisan. »",
                who="Julie & Thomas R.", role="Clients à {city}", caption="Le geste de l'artisan"),
        p4=dict(eyebrow="Réalisations & devis", title="Votre projet, en toute clarté", sub="Un devis détaillé après visite et prise de mesures.",
                tabs=["Cuisines", "Dressings", "Escaliers", "Mobilier"],
                head=("Nos univers", "Devis"),
                items=[("Cuisine en bois massif", "SUR-MESURE", "Plans de travail, façades et rangements dessinés pour votre pièce.", "Sur devis"),
                       ("Dressing & placards", "OPTIMISÉ", "Chaque centimètre exploité, finitions au choix.", "Sur devis"),
                       ("Escalier & garde-corps", "ARTISANAL", "Fabrication et pose, du bois brut à la finition.", "Sur devis"),
                       ("Table & mobilier", "PIÈCE UNIQUE", "Créations uniques, gravées à votre image.", "Sur devis")],
                foot_l="* Visite et devis gratuits", foot_r="Délai : sur rendez-vous", cta="Prendre rendez-vous"),
    ),
    "nature": dict(
        nav=["Accueil", "Réalisations", "Savoir-faire", "Entretien"],
        cta="Devis jardin", status="Devis gratuit",
        stats=[("12+", "ans d'expérience"), ("100%", "sur mesure"), ("300", "jardins créés"), ("4.9★", "avis clients")],
        p2=dict(eyebrow="Nos jardins", title="Des extérieurs qui donnent envie de sortir", sub="Création, terrasses, plantations : quelques jardins autour de {city}.",
                add="Demander un devis", foot="Étude gratuite", link="Voir le jardin",
                tags=[("leaf", "Création"), ("sun", "Terrasse"), ("droplet", "Arrosage"), ("heart", "Entretien")],
                metas=["Jardin livré", "Aménagement", "Système intégré", "Suivi saisonnier"],
                extra=("Un jardin qui vit toute l'année", "Végétaux adaptés au climat, pensés pour durer.")),
        p3=dict(eyebrow="Savoir-faire", title="Du plan à la dernière plantation", sub="Une équipe locale pour concevoir, réaliser et entretenir.",
                cards=[("leaf", "Conception paysagère", "Plans, palette végétale et ambiances adaptées à votre terrain.", "ÉTUDE"),
                       ("droplet", "Arrosage & durabilité", "Des choix économes en eau, résistants au soleil.", "ÉCO-RESPONSABLE")],
                quote="« Notre jardin est méconnaissable. L'équipe a été à l'écoute du début à la fin. »",
                who="Marie & Paul D.", role="Clients à {city}", caption="Un jardin pensé pour vous"),
        p4=dict(eyebrow="Prestations", title="Ce que nous faisons pour vous", sub="Un devis gratuit après visite de votre terrain.",
                tabs=["Création", "Terrasses", "Entretien", "Élagage"],
                head=("Nos prestations", "Devis"),
                items=[("Création de jardin", "CLÉ EN MAIN", "De l'étude à la plantation, un seul interlocuteur.", "Sur devis"),
                       ("Terrasse & allées", "DURABLE", "Bois, pierre, composite : un extérieur soigné.", "Sur devis"),
                       ("Entretien régulier", "ABONNEMENT", "Tonte, taille, désherbage : la tranquillité.", "Dès 45 €"),
                       ("Élagage & abattage", "SÉCURISÉ", "Intervention propre, évacuation incluse.", "Sur devis")],
                foot_l="* Devis gratuit et sans engagement", foot_r="Réponse sous 48h", cta="Demander un devis"),
    ),
    "gastro": dict(
        nav=["Accueil", "Soirées", "L'esprit", "La carte"],
        cta="Réserver", status="Service ouvert",
        stats=[("100%", "fait maison"), ("Midi & Soir", "service continu"), ("4.8★", "avis Google"), ("7j/7", "sur réservation")],
        p2=dict(eyebrow="Programmation & ambiance", title="Cette semaine chez {brand}", sub="Une table, une ambiance, des rendez-vous à ne pas manquer.",
                add="Réserver une table", foot="Sur réservation", link="Réserver",
                tags=[("utensils", "Plat du jour"), ("star", "Coup de cœur"), ("flame", "Incontournable"), ("heart", "Fait maison")],
                metas=["Midi & soir", "Chaque semaine", "Selon le marché", "Tous les jours"],
                extra=("Le rendez-vous convivial", "Une ambiance chaleureuse, à partager entre amis ou collègues.")),
        p3=dict(eyebrow="L'esprit", title="L'esprit {brand}", sub="Un lieu convivial pour se retrouver, déguster et décrocher.",
                cards=[("utensils", "Cuisine de saison", "Produits frais, recettes maison, ardoise renouvelée souvent.", "CUISINE MINUTE"),
                       ("glass", "Boissons & cocktails", "Sélection de vins, bières et cocktails signature.", "À SAVOURER")],
                quote="« L'adresse incontournable du quartier. On déconnecte totalement le temps d'un déjeuner ou d'un afterwork ! »",
                who="Julie & Thomas R.", role="Clients fidèles", caption="Un lieu pour se retrouver"),
        p4=dict(eyebrow="Ardoise & spécialités", title="La Carte du Chef", sub="Une cuisine préparée chaque jour avec des ingrédients frais.",
                tabs=["Entrées", "Plats", "Boissons", "Douceurs"],
                head=("Sélection gourmande", "Prix net"),
                items=[("Le plat signature", "INCONTOURNABLE", "La recette qui a fait la réputation de la maison, généreuse et fondante.", "12,50 €"),
                       ("Assiette du marché", "SPÉCIALITÉ", "Produits frais du jour, dressés comme à la maison.", "14,00 €"),
                       ("Planche à partager", "À PARTAGER", "Charcuteries, fromages affinés et pain frais.", "19,50 €"),
                       ("Dessert maison", "FAIT MAISON", "Un final gourmand préparé chaque matin.", "6,50 €")],
                foot_l="* Produits frais du marché & arrivages du jour", foot_r="Service continu le midi", cta="Bloquer une table"),
    ),
    "beaute": dict(
        nav=["Accueil", "Soins", "L'institut", "Tarifs"],
        cta="Prendre RDV", status="Sur rendez-vous",
        stats=[("10+", "ans d'expertise"), ("100%", "personnalisé"), ("Bio", "produits choisis"), ("4.9★", "avis clients")],
        p2=dict(eyebrow="Nos soins", title="Un moment rien que pour vous", sub="Soins, coupes et rituels pensés pour révéler votre beauté.",
                add="Prendre rendez-vous", foot="Sur rendez-vous", link="Réserver",
                tags=[("heart", "Visage"), ("scissors", "Coiffure"), ("sparkle", "Rituel"), ("leaf", "Naturel")],
                metas=["Soin signature", "Coupe & couleur", "Rituel détente", "Produits naturels"],
                extra=("Prenez soin de vous", "Une parenthèse de calme dans un cadre chaleureux.")),
        p3=dict(eyebrow="L'institut", title="Un lieu pensé pour votre bien-être", sub="Ambiance apaisante, gestes précis, produits soigneusement choisis.",
                cards=[("leaf", "Produits sélectionnés", "Des marques exigeantes, respectueuses de votre peau.", "NATUREL"),
                       ("heart", "Écoute & conseil", "Chaque soin adapté à vos envies et à votre rythme.", "PERSONNALISÉ")],
                quote="« Un accueil adorable et un résultat magnifique. Je ressors détendue à chaque fois. »",
                who="Sophie L.", role="Cliente fidèle", caption="Un cocon de douceur"),
        p4=dict(eyebrow="Carte des soins", title="Tarifs & prestations", sub="Réservez en ligne en quelques clics.",
                tabs=["Visage", "Corps", "Coiffure", "Mains & pieds"],
                head=("Nos prestations", "Tarif"),
                items=[("Soin visage éclat", "SIGNATURE", "Nettoyage, gommage et masque adaptés à votre peau.", "55 €"),
                       ("Massage relaxant", "60 MIN", "Un temps de détente profonde, huiles chaudes.", "70 €"),
                       ("Coupe & brushing", "SUR MESURE", "Conseil personnalisé et coiffage soigné.", "45 €"),
                       ("Beauté des mains", "EXPRESS", "Pose de vernis, soin des cuticules.", "30 €")],
                foot_l="* Tarifs indicatifs", foot_r="Réservation en ligne", cta="Réserver un soin"),
    ),
    "auto": dict(
        nav=["Accueil", "Prestations", "Atelier", "Tarifs"],
        cta="Prendre RDV", status="Atelier ouvert",
        stats=[("15+", "ans d'expérience"), ("48h", "délai moyen"), ("100%", "toutes marques"), ("4.8★", "avis clients")],
        p2=dict(eyebrow="Nos prestations", title="Entretien, réparation, carrosserie", sub="Toutes marques, avec un devis clair avant chaque intervention.",
                add="Prendre rendez-vous", foot="Devis gratuit", link="En savoir plus",
                tags=[("wrench", "Mécanique"), ("car", "Carrosserie"), ("bolt", "Diagnostic"), ("shield", "Contrôle")],
                metas=["Entretien", "Réparation", "Électronique", "Sécurité"],
                extra=("Votre véhicule entre de bonnes mains", "Diagnostic honnête et pièces de qualité.")),
        p3=dict(eyebrow="L'atelier", title="Un atelier équipé et transparent", sub="Outils modernes, techniciens formés, suivi de votre véhicule.",
                cards=[("bolt", "Diagnostic électronique", "Valise multimarques pour trouver la panne rapidement.", "PRÉCIS"),
                       ("shield", "Garantie travaux", "Pièces de qualité, main-d'œuvre garantie.", "GARANTIE")],
                quote="« Diagnostic clair, prix annoncé respecté, voiture rendue à l'heure. Rien à redire. »",
                who="Nicolas B.", role="Client à {city}", caption="Précision & transparence"),
        p4=dict(eyebrow="Tarifs & devis", title="Des prix annoncés d'avance", sub="Un devis détaillé avant toute intervention.",
                tabs=["Entretien", "Freinage", "Carrosserie", "Pneus"],
                head=("Nos forfaits", "Tarif"),
                items=[("Vidange & filtres", "POPULAIRE", "Huile, filtres et contrôle des niveaux.", "Dès 89 €"),
                       ("Freinage complet", "SÉCURITÉ", "Plaquettes, disques et purge du circuit.", "Sur devis"),
                       ("Diagnostic électronique", "RAPIDE", "Lecture des défauts et rapport détaillé.", "49 €"),
                       ("Carrosserie & peinture", "FINITION", "Débosselage, retouches, remise en état.", "Sur devis")],
                foot_l="* Prix TTC indicatifs", foot_r="Rendez-vous sous 48h", cta="Prendre rendez-vous"),
    ),
}
_ACTION = {"batiment": "Devis en ligne guidé", "bois": "Projet en ligne guidé", "nature": "Devis en ligne guidé", "auto": "RDV en ligne",
           "gastro": "Réservation en ligne", "beaute": "RDV en ligne", "default": "Contact en ligne"}
for _n, _p in PROFILES.items():
    _p["stats"] = [["100%", "adapté au mobile"], ["Google", "visibilité locale"], ["2 min", "pour vous contacter"], ["1 clic", _ACTION.get(_n, "Contact en ligne").lower()]]
    _p["p3"].update(quote="« Vos meilleurs avis clients, mis en avant ici avec leur note. »", who="Avis clients",
                    role="Synchronisés avec votre fiche Google")
PROFILES["default"] = dict(PROFILES["batiment"], cta="Nous contacter", status="Disponible",
                           nav=["Accueil", "Réalisations", "Savoir-faire", "Contact"])

ICONS = {
    "flame": "M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.4-.5-2-1-3-1-2.1-.2-4 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.2.4-2.3 1-3a2.5 2.5 0 0 0 2.5 2.5z",
    "utensils": "M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2M7 2v20M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3zm0 0v7",
    "wrench": "M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.8-3.8a6 6 0 0 1-7.9 7.9l-6.9 6.9a2.1 2.1 0 0 1-3-3l6.9-6.9a6 6 0 0 1 7.9-7.9z",
    "hammer": "M15 12l-8.5 8.5a2.1 2.1 0 0 1-3-3L12 9M17.6 15L22 10.6M20.9 11.7l-1.2-1.2a3 3 0 0 1-.9-2.1V7l-3-3-3.3 1.3a3 3 0 0 1 2.4 1.6L16 8",
    "ruler": "M21.3 8.7 8.7 21.3a1 1 0 0 1-1.4 0l-4.6-4.6a1 1 0 0 1 0-1.4L15.3 2.7a1 1 0 0 1 1.4 0l4.6 4.6a1 1 0 0 1 0 1.4zM7.5 10.5l2 2M10.5 7.5l2 2M13.5 4.5l2 2M4.5 13.5l2 2",
    "calendar": "M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z",
    "clock": "M12 6v6l4 2M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z",
    "phone": "M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z",
    "pin": "M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0zM12 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
    "star": "M12 2l3.1 6.3 6.9 1-5 4.9 1.2 6.9L12 17.8 5.8 21l1.2-6.9-5-4.9 6.9-1z",
    "shield": "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zM9 12l2 2 4-4",
    "check": "M20 6 9 17l-5-5",
    "arrow": "M5 12h14M12 5l7 7-7 7",
    "leaf": "M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.5 19 2c1 2 2 4.2 2 8 0 5.5-4.8 10-10 10zM2 21c0-3 1.9-5.400 5.100-6 2.400-.5 4.900-2 5.900-3",
    "scissors": "M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM20 4 8.1 15.9M14.500 14.500 20 20M8.100 8.100 12 12",
    "car": "M5 17H3v-5l2-5h11l3 5h2v5h-2M7 17h8M6.500 20a1.500 1.500 0 1 0 0-3 1.500 1.500 0 0 0 0 3zM16.500 20a1.500 1.500 0 1 0 0-3 1.500 1.500 0 0 0 0 3z",
    "droplet": "M12 22a7 7 0 0 0 7-7c0-2-1-3.900-3-5.500s-3.500-4-4-6.500c-.5 2.500-2 4.900-4 6.500C6 11.100 5 13 5 15a7 7 0 0 0 7 7z",
    "bolt": "M13 2 3 14h9l-1 8 10-12h-9z",
    "heart": "M20.800 4.600a5.500 5.500 0 0 0-7.800 0L12 5.700l-1.100-1.100a5.500 5.500 0 0 0-7.800 7.800l1.100 1.100L12 21.200l7.800-7.700 1.100-1.100a5.500 5.500 0 0 0 0-7.800z",
    "thermometer": "M14 4v10.500a4 4 0 1 1-4 0V4a2 2 0 0 1 4 0z",
    "sun": "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.200 4.200l1.400 1.400M18.400 18.400l1.400 1.400M1 12h2M21 12h2M4.200 19.800l1.400-1.400M18.400 5.600l1.400-1.400",
    "sparkle": "M12 3l1.900 5.800L20 10.700l-6.100 1.900L12 18.500l-1.900-5.900L4 10.700l6.100-1.900z",
    "glass": "M8 22h8M12 15v7M5 3h14l-1 6a6 6 0 0 1-12 0z",
    "menu": "M4 7h16M4 12h16M4 17h16",
    "home": "M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM9 22V12h6v10",
    "key": "M21 2l-2 2m-7.600 7.600a5.500 5.500 0 1 1-7.800 7.800 5.500 5.500 0 0 1 7.800-7.800zm0 0L15.500 7.500m0 0l3 3L22 7l-3-3m-3.500 3.500L19 4",
    "camera": "M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2zM12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
    "user": "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
    "shutter": "M3 3h18v18H3zM3 9h18M3 15h18",
}


def icon(name: str, size: int = 16, fill: bool = False) -> str:
    d = ICONS.get(name, ICONS["sparkle"])
    f = "currentColor" if fill else "none"
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="{f}" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round" style="flex:none"><path d="{d}"/></svg>')


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def theme_name(data: dict) -> str:
    forced = data.get("THEME")
    if isinstance(forced, str) and forced in THEMES:
        return forced
    if data.get("SECTEUR") in THEMES:
        return data["SECTEUR"]
    haystack = normalize(" ".join(
        str(data.get(k, "")) for k in ("BRAND_NAME", "BADGE_TEXT", "HERO_TITLE", "HERO_SUBTITLE")
    )) + " "
    for name, theme in THEMES.items():
        if any(kw in haystack for kw in theme["keywords"]):
            return name
    return "default"


def font_url(*families: str) -> str:
    fams = "&".join(f"family={f.replace(' ', '+')}:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400;1,500;1,600;1,700"
                    for f in dict.fromkeys(families))
    return f"https://fonts.googleapis.com/css2?{fams}&display=swap"


def format_image(src: str) -> str:
    src = (src or "").strip()
    if not src:
        return ""
    if src.startswith(("http://", "https://")):
        return src
    return f"file://{os.path.abspath(src)}"


def esc(value) -> str:
    # espace insécable avant ? ! : ; (typographie française, évite un « ? » orphelin en début de ligne)
    return re.sub(r" ([?!:;»])", "\u00a0\\1", htmllib.escape(str(value)))


def mix(c1: str, c2: str, w: float) -> str:
    """Mélange 2 couleurs hex : w=0 -> c1, w=1 -> c2."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * w):02x}" for x, y in zip(a, b))


def logo_color(path: str):
    """Couleur dominante (saturée) du logo, pour accorder toute la maquette à la marque."""
    try:
        from PIL import Image
        im = Image.open(path).convert("RGBA")
        im.thumbnail((96, 96))
        best, score = None, 0
        counts = {}
        for r, g, b, a in im.getdata():
            if a < 200:
                continue
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if s < .35 or v < .25 or v > .95:
                continue
            key = (r // 24, g // 24, b // 24)
            counts[key] = counts.get(key, [0, (r, g, b)])
            counts[key][0] += 1
        for n, (r, g, b) in counts.values():
            if n > score:
                best, score = (r, g, b), n
        return "#%02x%02x%02x" % best if best else None
    except Exception:
        return None


def build_theme(data: dict) -> dict:
    name = theme_name(data)
    t = dict(THEMES[name])
    forced = data.get("THEME")
    if isinstance(forced, dict):
        t.update(forced)
    t["name"] = name
    t["hot"] = t["accent"]
    if not isinstance(forced, dict) or "accent" not in forced:
        lc = data.get("_logo_path") and logo_color(data["_logo_path"])
        if lc:  # accent = couleur du logo ; l'ancien accent devient la couleur d'action
            t["accent"] = lc
            t["soft"] = mix(lc, t["bg"], .85)
    t["accent_lt"] = mix(t["accent"], "#ffffff", .38)
    t["ink"] = mix(t["text"], "#000000", .3)
    t["dark"] = mix(t["text"], "#000000", .62)
    return t


def profile_for(t: dict, data: dict) -> dict:
    base = json.loads(json.dumps(PROFILES.get(t["name"], PROFILES["default"])))
    for k, v in (data.get("SITE") or {}).items():  # surcharge fine possible depuis prospect.json
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k].update(v)
        else:
            base[k] = v
    if data.get("CONFIGURATEUR"):
        base.setdefault("config", json.loads(json.dumps(PROFILES["batiment"]["config"])))
        if "nav" not in (data.get("SITE") or {}):
            base["nav"][3] = "Devis en ligne"
    sub = {"brand": data["BRAND_NAME"], "city": data.get("CITY", "votre région")}

    def fill(x):
        if isinstance(x, str):
            return x.replace("{brand}", sub["brand"]).replace("{city}", sub["city"])
        if isinstance(x, list):
            return [fill(i) for i in x]
        if isinstance(x, tuple):
            return tuple(fill(i) for i in x)
        if isinstance(x, dict):
            return {k: fill(v) for k, v in x.items()}
        return x
    return fill(base)


# ---------------------------------------------------------------------------
# 1) Le site : 4 pages différentes (héros plein écran, cartes, bento, carte/tarifs)
# ---------------------------------------------------------------------------
def initials(name: str) -> str:
    words = [w for w in re.split(r"[\s'’-]+", name) if w and w[0].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or name[:1].upper()


def logo_html(t: dict, data: dict, size: int = 42) -> str:
    if data.get("_logo_url"):
        return (f'<span class="lg" style="width:{size}px;height:{size}px"><img src="{esc(data["_logo_url"])}" '
                f'style="width:100%;height:100%;object-fit:contain;display:block"></span>')
    return (f'<span class="lg mono" style="width:{size}px;height:{size}px;font-size:{round(size * .42)}px">'
            f'{esc(initials(data["BRAND_NAME"]))}</span>')


def site_css(t: dict) -> str:
    return f"""
    :root {{ --bg:{t['bg']}; --surface:{t['surface']}; --text:{t['text']}; --muted:{t['muted']}; --accent:{t['accent']};
      --lt:{t['accent_lt']}; --hot:{t['hot']}; --hot-text:{t['accent_text']}; --soft:{t['soft']}; --border:{t['border']};
      --ink:{t['ink']}; --dark:{t['dark']}; --pad:56px; --hf:'{t['heading_font']}', serif; }}
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    html,body {{ height:100%; }}
    body {{ overflow:hidden; position:relative; background:var(--bg); color:var(--text);
            font-family:'{t['body_font']}', sans-serif; -webkit-font-smoothing:antialiased; }}
    h1,h2,h3,.brand b {{ font-family:var(--hf); }}
    img {{ display:block; }}
    /* --- barre de navigation flottante --- */
    .nav {{ position:absolute; z-index:30; top:18px; left:50%; transform:translateX(-50%); width:calc(100% - 2*var(--pad) + 24px);
            max-width:1190px; display:flex; align-items:center; gap:22px; padding:9px 12px 9px 20px; border-radius:999px;
            background:var(--ink); color:#fff; box-shadow:0 24px 44px -20px rgba(0,0,0,.55); }}
    .nav.glass {{ background:rgba(16,12,10,.62); backdrop-filter:blur(16px); border:1px solid rgba(255,255,255,.14); box-shadow:none; }}
    .brand {{ display:flex; align-items:center; gap:12px; }}
    .lg {{ border-radius:12px; overflow:hidden; flex:none; display:block; }}
    .lg.mono {{ display:grid; place-items:center; font-family:var(--hf); font-weight:800; color:#fff; letter-spacing:.02em;
                background:linear-gradient(135deg,var(--accent),{mix(t['accent'], '#000000', .35)}); box-shadow:inset 0 0 0 1.5px rgba(255,255,255,.25); }}
    .brand b {{ display:block; font-size:var(--bs,19px); letter-spacing:.16em; text-transform:uppercase; font-weight:700; line-height:1.1; white-space:nowrap; }}
    .brand small {{ display:block; margin-top:3px; font-size:9.5px; letter-spacing:.3em; text-transform:uppercase; color:var(--lt); font-weight:600; }}
    .links {{ display:flex; gap:26px; margin:0 auto; font-size:11.5px; font-weight:600; letter-spacing:.12em; text-transform:uppercase; color:rgba(255,255,255,.68); }}
    .links span {{ padding:6px 0; position:relative; white-space:nowrap; }}
    .links .on {{ color:#fff; }} .links .on::after {{ content:""; position:absolute; left:0; right:0; bottom:0; height:2px; border-radius:2px; background:var(--hot); }}
    .status {{ display:flex; align-items:center; gap:7px; font-size:11.5px; font-weight:600; color:#4ade9a; padding:7px 13px; border-radius:999px;
               border:1px solid rgba(74,222,154,.4); background:rgba(74,222,154,.08); white-space:nowrap; }}
    .status::before {{ content:""; width:7px; height:7px; border-radius:50%; background:#4ade9a; box-shadow:0 0 0 3px rgba(74,222,154,.2); }}
    .btn {{ display:inline-flex; align-items:center; gap:9px; background:var(--hot); color:var(--hot-text); padding:11px 20px; border-radius:999px;
            font-weight:700; font-size:11.5px; letter-spacing:.1em; text-transform:uppercase; white-space:nowrap;
            box-shadow:0 12px 22px -10px var(--hot); }}
    .btn.lg2 {{ padding:15px 28px; font-size:12px; }}
    .btn.ghost {{ background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.28); color:#fff; box-shadow:none; backdrop-filter:blur(8px); }}
    .btn.dk {{ background:var(--ink); color:#fff; box-shadow:0 14px 26px -12px rgba(0,0,0,.6); }}
    .btn.dk svg {{ color:var(--lt); }}
    .burger {{ display:none; width:38px; height:38px; border-radius:50%; background:rgba(255,255,255,.1); place-items:center; }}
    .chip {{ display:inline-flex; align-items:center; gap:8px; font-size:11px; font-weight:700; letter-spacing:.16em; text-transform:uppercase;
             color:var(--accent); background:var(--soft); padding:8px 15px; border-radius:999px; }}
    .eyebrow {{ font-size:11px; font-weight:700; letter-spacing:.3em; text-transform:uppercase; color:var(--accent); }}
    /* --- page 1 : héros plein écran --- */
    .hero {{ position:absolute; inset:0; }}
    .hero > img {{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }}
    .hero::after {{ content:""; position:absolute; inset:0;
       background:linear-gradient(180deg, rgba(0,0,0,.5) 0%, rgba(0,0,0,.42) 40%, {t['dark']}e6 100%); }}
    .hero-c {{ position:absolute; z-index:5; inset:0 0 150px; display:flex; flex-direction:column; align-items:center; justify-content:center;
               text-align:center; padding:70px 64px 0; color:#fff; }}
    .hero-c .chip {{ background:rgba(0,0,0,.35); color:var(--lt); border:1px solid rgba(255,255,255,.2); backdrop-filter:blur(8px); }}
    h1 {{ font-size:var(--h,54px); line-height:1.08; font-weight:700; letter-spacing:-.015em; margin:24px 0 18px; text-shadow:0 6px 30px rgba(0,0,0,.35); }}
    h1 em {{ display:block; font-weight:500; color:rgba(255,255,255,.82); }}
    .lead {{ max-width:640px; font-size:17px; line-height:1.6; color:rgba(255,255,255,.82); }}
    .acts {{ display:flex; gap:14px; margin-top:28px; }}
    .facts {{ position:absolute; z-index:5; left:50%; bottom:34px; transform:translateX(-50%); display:flex; gap:16px; width:calc(100% - 2*var(--pad) - 130px); max-width:1000px; }}
    .facts div {{ flex:1; text-align:center; padding:15px 12px; border-radius:16px; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.16);
                  backdrop-filter:blur(14px); color:#fff; }}
    .facts b {{ display:block; font-family:var(--hf); font-size:25px; color:var(--lt); }}
    .facts span {{ font-size:10px; letter-spacing:.14em; text-transform:uppercase; color:rgba(255,255,255,.7); font-weight:600; }}
    /* --- pages 2-4 --- */
    .page {{ position:absolute; inset:0; padding:112px var(--pad) 30px; display:flex; flex-direction:column; gap:22px; }}
    .page.dark {{ background:radial-gradient(900px 500px at 85% 0%, {mix(t['accent'], t['dark'], .82)}, transparent 70%), var(--dark); color:#fff; }}
    .head {{ display:flex; justify-content:space-between; align-items:flex-end; gap:30px; }}
    .head > div:first-child {{ max-width:820px; }}
    .head h2 {{ font-size:var(--h2,42px); line-height:1.08; font-weight:700; letter-spacing:-.012em; margin:14px 0 10px; }}
    .head p {{ font-size:15px; line-height:1.55; color:var(--muted); max-width:560px; }}
    .head.c {{ flex-direction:column; align-items:center; text-align:center; gap:0; }} .head.c p {{ max-width:620px; }}
    .head.c h2 {{ margin:10px 0 8px; }}
    .dark .head p {{ color:rgba(255,255,255,.62); }} .dark .eyebrow {{ color:var(--lt); }}
    .cards {{ flex:1; min-height:0; display:grid; grid-template-columns:repeat(4,1fr); gap:18px; }}
    .card {{ background:var(--surface); border:1px solid var(--border); border-radius:26px; overflow:hidden; display:flex; flex-direction:column;
             box-shadow:0 22px 44px -26px rgba(0,0,0,.35); min-width:0; }}
    .card .ph {{ height:43%; position:relative; flex:none; }} .card .ph img {{ width:100%; height:100%; object-fit:cover; }}
    .num {{ position:absolute; top:14px; left:14px; width:50px; padding:7px 0; text-align:center; border-radius:13px; background:var(--ink); color:#fff; line-height:1.15; }}
    .num small {{ display:block; font-size:8.5px; letter-spacing:.14em; color:var(--lt); font-weight:700; }} .num b {{ font-family:var(--hf); font-size:20px; }}
    .tag {{ position:absolute; top:18px; right:14px; display:flex; align-items:center; gap:6px; padding:6px 11px; border-radius:999px; background:rgba(255,255,255,.94);
            font-size:10.5px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; color:#1a1a1a; }}
    .tag svg {{ color:var(--hot); }}
    .card .bd {{ flex:1; padding:16px 20px 0; display:flex; flex-direction:column; min-height:0; }}
    .meta {{ display:flex; align-items:center; gap:7px; font-size:12px; font-weight:600; color:var(--hot); }}
    .card h3 {{ font-size:19px; line-height:1.2; margin:9px 0 7px; font-weight:700; }}
    .card p {{ font-size:13px; line-height:1.5; color:var(--muted); display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }}
    .card .ft {{ margin-top:auto; border-top:1px solid var(--border); padding:13px 0 15px; display:flex; justify-content:space-between; align-items:center; font-size:12px; color:var(--muted); }}
    .card .ft b {{ color:var(--hot); display:flex; align-items:center; gap:6px; font-weight:700; }}
    /* bento */
    .bento {{ flex:1; min-height:0; display:grid; grid-template-columns:repeat(4,1fr); grid-template-rows:1fr 1fr; gap:16px; }}
    .tile {{ border-radius:26px; overflow:hidden; position:relative; min-width:0; min-height:0; }}
    .tile.ph > img {{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }}
    .tile.ph::after {{ content:""; position:absolute; inset:0; background:linear-gradient(180deg, transparent 35%, rgba(0,0,0,.82)); }}
    .tile.ph .tx {{ position:absolute; z-index:2; left:26px; right:26px; bottom:22px; color:#fff; }}
    .tx small {{ font-size:10.5px; letter-spacing:.2em; font-weight:700; color:rgba(255,255,255,.78); text-transform:uppercase; }}
    .tx h3 {{ font-size:23px; margin:5px 0 6px; }} .tx p {{ font-size:13px; line-height:1.5; color:rgba(255,255,255,.82); max-width:520px; }}
    .tile.info {{ background:var(--surface); border:1px solid var(--border); padding:22px; display:flex; flex-direction:column; }}
    .ico {{ width:44px; height:44px; border-radius:14px; display:grid; place-items:center; background:var(--soft); color:var(--hot); }}
    .tile.info h3 {{ font-size:18px; margin:16px 0 8px; }} .tile.info p {{ font-size:13px; line-height:1.55; color:var(--muted); }}
    .tile.info .lab {{ margin-top:auto; font-size:10.5px; letter-spacing:.14em; font-weight:700; color:var(--hot); }}
    .tile.quote {{ background:var(--dark); color:#fff; padding:22px; display:flex; flex-direction:column; }}
    .stars {{ display:flex; gap:3px; color:#fbbf24; }}
    .tile.quote q {{ quotes:none; margin-top:14px; font-style:italic; font-size:15px; line-height:1.55; color:rgba(255,255,255,.9); }}
    .tile.quote .who {{ margin-top:auto; border-top:1px solid rgba(255,255,255,.14); padding-top:12px; font-size:12.5px; font-weight:700; }}
    .who small {{ display:block; font-weight:400; color:rgba(255,255,255,.5); font-size:11px; margin-top:2px; }}
    /* carte / tarifs (sombre) */
    .tabs {{ display:flex; padding:5px; gap:2px; border-radius:999px; border:1px solid rgba(255,255,255,.14); background:rgba(255,255,255,.05); }}
    .tabs span {{ padding:10px 20px; font-size:11.5px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; color:rgba(255,255,255,.72); border-radius:999px; white-space:nowrap; }}
    .tabs .on {{ background:var(--hot); color:var(--hot-text); }}
    .panels {{ flex:1; min-height:0; display:grid; grid-template-columns:1.45fr 1fr; gap:22px; }}
    .panel {{ border-radius:30px; padding:24px 26px; background:rgba(255,255,255,.055); border:1px solid rgba(255,255,255,.12); display:flex; flex-direction:column; min-height:0; }}
    .ph-h {{ display:flex; justify-content:space-between; font-size:12px; letter-spacing:.16em; text-transform:uppercase; color:rgba(255,255,255,.6); padding-bottom:12px; border-bottom:1px solid rgba(255,255,255,.12); margin-bottom:10px; }}
    .row {{ flex:1; max-height:96px; display:flex; justify-content:space-between; align-items:center; gap:18px; padding:11px 16px; margin-top:9px; border-radius:18px; background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.08); }}
    .row:first-of-type {{ background:rgba(255,255,255,.09); border-color:{t['accent']}88; margin-top:0; }}
    .row h4 {{ font-family:var(--hf); font-size:17px; font-weight:700; display:flex; align-items:center; gap:10px; }}
    .row h4 i {{ font:700 9px 'Inter'; font-style:normal; letter-spacing:.06em; padding:3px 9px; border-radius:999px; border:1px solid {t['accent']}; color:var(--lt); background:{t['accent']}22; text-transform:uppercase; }}
    .row p {{ font-size:12px; line-height:1.4; color:rgba(255,255,255,.58); margin-top:4px; }}
    .row .val {{ font-family:var(--hf); font-size:17px; font-weight:700; color:var(--lt); white-space:nowrap; }}
    .pfoot {{ margin-top:auto; display:flex; justify-content:space-between; align-items:center; padding-top:14px; border-top:1px solid rgba(255,255,255,.12); font-size:12px; color:rgba(255,255,255,.55); }}
    .pfoot b {{ color:var(--lt); font-weight:600; }}
    .feat .img {{ height:50%; flex:none; border-radius:20px; overflow:hidden; position:relative; border:1px solid rgba(255,255,255,.14); }}
    .feat .img img {{ width:100%; height:100%; object-fit:cover; }}
    .feat .img span {{ position:absolute; top:12px; left:12px; padding:6px 12px; border-radius:999px; background:rgba(0,0,0,.6); backdrop-filter:blur(8px); font-size:10px; font-weight:700; letter-spacing:.14em; text-transform:uppercase; color:var(--lt); }}
    .feat h3 {{ font-size:23px; margin:16px 0 8px; line-height:1.15; }} .feat p {{ font-size:13.5px; line-height:1.55; color:rgba(255,255,255,.66); }}
    .feat .go {{ color:var(--lt); font-weight:700; letter-spacing:.1em; text-transform:uppercase; display:flex; gap:8px; align-items:center; }}
    /* configurateur de devis */
    .stepper {{ display:flex; align-items:center; gap:10px; }}
    .st {{ display:flex; align-items:center; gap:9px; font-size:11.5px; font-weight:700; letter-spacing:.1em; text-transform:uppercase; color:rgba(255,255,255,.5); white-space:nowrap; }}
    .st i {{ width:30px; height:30px; border-radius:50%; display:grid; place-items:center; border:1.5px solid rgba(255,255,255,.25); font-style:normal; font-size:12px; }}
    .st.done {{ color:rgba(255,255,255,.8); }} .st.done i {{ background:var(--lt); border-color:var(--lt); color:var(--dark); }}
    .st.on {{ color:#fff; }} .st.on i {{ background:var(--hot); border-color:var(--hot); color:var(--hot-text); }}
    .sep {{ width:30px; height:2px; background:rgba(255,255,255,.18); }}
    .wiz h3 {{ font-size:25px; line-height:1.15; }} .wiz > p {{ font-size:13.5px; color:rgba(255,255,255,.62); margin:6px 0 18px; }}
    .opts {{ flex:1; min-height:0; display:grid; grid-template-columns:repeat(3,1fr); grid-auto-rows:1fr; gap:12px; }}
    .opt {{ position:relative; border-radius:20px; padding:16px; border:1.5px solid rgba(255,255,255,.14); background:rgba(255,255,255,.05);
            display:flex; flex-direction:column; justify-content:space-between; font-weight:700; font-size:15px; }}
    .opt .ico {{ background:rgba(255,255,255,.08); color:var(--lt); width:42px; height:42px; }}
    .opt.sel {{ border-color:var(--hot); background:{mix(t['hot'], t['dark'], .82)}; }} .opt.sel .ico {{ background:var(--hot); color:var(--hot-text); }}
    .opt.sel::after {{ content:"✓"; position:absolute; top:12px; right:14px; width:22px; height:22px; border-radius:50%; background:var(--hot); color:var(--hot-text); font-size:12px; display:grid; place-items:center; }}
    .wnav {{ display:flex; justify-content:space-between; align-items:center; margin-top:16px; }}
    .wnav .back {{ font-size:12px; font-weight:700; letter-spacing:.1em; text-transform:uppercase; color:rgba(255,255,255,.6); }}
    .ticket {{ background:#fff; color:#1a1a1a; border:0; position:relative; }}
    .ticket .th {{ display:flex; justify-content:space-between; align-items:center; padding-bottom:14px; border-bottom:2px dashed #d9dde3; }}
    .ticket .th h3 {{ font-size:20px; margin:0; color:var(--ink); }} .ticket .th small {{ font-size:11px; font-weight:700; letter-spacing:.14em; color:#8a93a0; }}
    .ticket .tr {{ display:flex; justify-content:space-between; gap:14px; padding:11px 0; border-bottom:1px solid #eceff3; font-size:13px; }}
    .ticket .tr span {{ color:#7b8492; }} .ticket .tr b {{ color:var(--ink); text-align:right; }}
    .ticket .bdg {{ margin-top:14px; align-self:flex-start; display:flex; align-items:center; gap:8px; padding:8px 14px; border-radius:999px; font-size:11.5px; font-weight:700; background:var(--soft); color:var(--ink); }}
    .ticket .bdg svg {{ color:var(--hot); }}
    .ticket .btn {{ margin-top:auto; justify-content:center; }}
    .callfab {{ display:none; }}
    /* --- mobile (390px) --- */
    @media (max-width:640px) {{
      :root {{ --pad:20px; }}
      .nav {{ top:46px; width:calc(100% - 28px); padding:7px 8px 7px 12px; gap:10px; }}
      .brand {{ gap:9px; }} .brand {{ min-width:0; flex:1; }} .brand > div {{ min-width:0; }} .brand b {{ font-size:min(12.5px, calc(var(--bs,19px) * .68)); letter-spacing:.1em; overflow:hidden; text-overflow:ellipsis; }} .brand small {{ font-size:8px; }}
      .links, .status {{ display:none; }} .nav .btn {{ margin-left:auto; padding:9px 13px; font-size:10px; }} .burger {{ display:grid; }}
      .hero-c {{ inset:0 0 130px; padding:110px 22px 0; }}
      h1 {{ font-size:calc(var(--h,54px) * .56); margin:16px 0 12px; }} h1 em {{ display:inline; }} h1 br {{ display:none; }}
      .lead {{ font-size:14px; }} .acts {{ margin-top:20px; gap:10px; flex-wrap:wrap; justify-content:center; }}
      .btn.lg2 {{ padding:13px 20px; font-size:11px; }}
      .facts {{ width:calc(100% - 28px); bottom:28px; gap:8px; }} .facts div {{ padding:11px 4px; border-radius:13px; }}
      .facts b {{ font-size:15px; }} .facts span {{ font-size:7.5px; letter-spacing:.06em; }} .facts div:nth-child(n+3) {{ display:none; }}
      .facts div:nth-child(1), .facts div:nth-child(2) {{ }}
      .page {{ padding:112px var(--pad) 0; gap:18px; }}
      .head {{ flex-direction:column; align-items:flex-start; gap:14px; }} .head h2 {{ font-size:calc(var(--h2,42px) * .68); margin:12px 0 8px; }}
      .head p {{ font-size:13.5px; }} .head > .btn, .tabs {{ display:none; }}
      .cards {{ grid-template-columns:none; grid-auto-flow:column; grid-auto-columns:80%; overflow:hidden; margin-right:calc(-1 * var(--pad)); padding-bottom:30px; }}
      .card .ph {{ height:190px; }} .card .bd {{ padding-top:18px; }}
      .bento {{ grid-template-columns:none; grid-template-rows:none; grid-auto-flow:column; grid-auto-columns:78%; overflow:hidden; margin-right:calc(-1 * var(--pad)); padding-bottom:30px; }}
      .tile {{ grid-column:auto !important; }} .brand small {{ white-space:nowrap; letter-spacing:.18em; }}
      .pfoot {{ font-size:10.5px; }}
      .callfab {{ display:flex; position:absolute; z-index:40; left:16px; right:16px; bottom:16px; align-items:center; justify-content:center; gap:10px;
                  padding:15px 20px; border-radius:999px; background:var(--hot); color:var(--hot-text); font-weight:800; font-size:13px; letter-spacing:.08em;
                  text-transform:uppercase; box-shadow:0 18px 34px -10px rgba(0,0,0,.55), 0 0 0 5px rgba(255,255,255,.25); }}
      .callfab small {{ font-weight:600; letter-spacing:.04em; opacity:.9; text-transform:none; font-size:12px; }}
      body:has(.callfab) .facts {{ bottom:96px; }} body:has(.callfab) .hero-c {{ inset:0 0 200px; }}
      body:has(.callfab) .page {{ padding-bottom:84px; }} body:has(.callfab) .cards, body:has(.callfab) .bento {{ padding-bottom:0; }}
      body:has(.callfab) .nav .btn {{ display:none; }} body:has(.callfab) .nav {{ padding-right:10px; }} body:has(.callfab) .burger {{ margin-left:auto; }}
      .wiz > p {{ display:none; }} .wiz h3 {{ margin-bottom:14px; }} .opts {{ grid-auto-rows:78px; flex:none; gap:10px; }} .opt .ico {{ width:34px; height:34px; }}
      .stepper .st span, .stepper .sep {{ display:none; }} .stepper {{ gap:8px; }} .ticket {{ display:none; }}
      .opts {{ grid-template-columns:repeat(2,1fr); }} .wiz h3 {{ font-size:19px; }} .opt {{ font-size:13px; padding:12px; }}
      .panels {{ grid-template-columns:1fr; }} .feat {{ display:none; }} .panel {{ border-radius:24px; padding:18px; }}
      .row {{ padding:12px 14px; }} .row p {{ display:none; }} .row h4 {{ font-size:15px; flex-wrap:wrap; gap:6px; }}
    }}
    """


def split_title(title: str):
    words = title.split()
    if len(words) < 4:
        return title, ""
    half, best, pos = len(title) / 2, 0, 0
    cands = []
    for i, w in enumerate(words[:-1]):
        pos += len(w) + 1
        cands.append((abs(pos - half), i + 1))
    best = min(cands)[1]
    return " ".join(words[:best]), " ".join(words[best:])


def nav_html(t, data, prof, active, glass=False):
    links = "".join(f'<span class="{"on" if i == active else ""}">{esc(n)}</span>' for i, n in enumerate(prof["nav"]))
    name = data["BRAND_NAME"]
    bs = 19 if len(name) <= 16 else 15 if len(name) <= 24 else 12
    sub = f"<small>{esc(data.get('CITY', ''))}</small>" if data.get("CITY") else ""
    return (f'<div class="nav {"glass" if glass else ""}"><div class="brand" style="--bs:{bs}px">{logo_html(t, data, 42)}'
            f'<div><b>{esc(name)}</b>{sub}</div></div><div class="links">{links}</div>'
            f'<span class="status">{esc(prof["status"])}</span>'
            f'<span class="btn">{icon("calendar", 14)}{esc(prof["cta"])}</span>'
            f'<span class="burger">{icon("menu", 18)}</span></div>' + fab_html(data, prof))


def fab_html(data, prof):
    if not data.get("PHONE"):
        return ""
    label = data.get("CALL_LABEL") or prof["status"]
    return f'<div class="callfab">{icon("phone", 18)}<span>{esc(label)}</span><small>{esc(data["PHONE"])}</small></div>'


def shell_html(t, body, extra_body_class=""):
    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="{font_url(t['heading_font'], t['body_font'], 'Inter')}" rel="stylesheet">
    <style>{site_css(t)}</style></head><body>{body}</body></html>"""


def page_home(t, data, prof):
    a, b = split_title(data["HERO_TITLE"])
    longest = max(len(a), len(b), 1)
    h = max(38, min(68, int(1000 / (longest * .56))))
    metier = re.split(r"\s[—–-]\s", data.get("BADGE_TEXT", ""))[0].strip()
    badge = f"{metier} · {data['CITY']}" if data.get("CITY") and len(metier) < 48 else data.get("BADGE_TEXT", metier)
    facts = "".join(f"<div><b>{esc(v)}</b><span>{esc(l)}</span></div>" for v, l in prof["stats"])
    return shell_html(t, f"""
      {nav_html(t, data, prof, 0, glass=True)}
      <div class="hero"><img src="{esc(data['HERO_IMG'])}"></div>
      <div class="hero-c">
        <span class="chip">{icon('sparkle', 14)}{esc(badge)}</span>
        <h1 style="--h:{h}px">{esc(a)}{'<br> ' if b else ''}<em>{esc(b)}</em></h1>
        <p class="lead">{esc(data['HERO_SUBTITLE'])}</p>
        <div class="acts"><span class="btn lg2">{icon('calendar', 15)}{esc(prof['cta'])}</span>
          <span class="btn ghost lg2">{icon('arrow', 15)}{esc(prof['nav'][1])}</span></div>
      </div>
      <div class="facts">{facts}</div>""")


def page_cards(t, data, prof):
    p = prof["p2"]
    imgs = ["IMG_REALISATION", "IMG_FINITION", "IMG_ATELIER", "HERO_IMG"]
    titles = [(data["TITLE_IMG_2"], data["DESC_IMG_2"]), (data["TITLE_IMG_3"], data["DESC_IMG_3"]),
              (data["TITLE_IMG_4"], data["DESC_IMG_4"]), p["extra"]]
    cards = ""
    for i in range(4):
        tg_icon, tg = p["tags"][i]
        cards += f"""<div class="card"><div class="ph"><img src="{esc(data[imgs[i]])}">
          <div class="num"><small>N°</small><b>{i + 1:02d}</b></div><span class="tag">{icon(tg_icon, 12)}{esc(tg)}</span></div>
          <div class="bd"><div class="meta">{icon('check', 14)}{esc(p['metas'][i])}</div><h3>{esc(titles[i][0])}</h3><p>{esc(titles[i][1])}</p>
          <div class="ft"><span>{esc(p['foot'])}</span><b>{esc(p['link'])}{icon('arrow', 13)}</b></div></div></div>"""
    return shell_html(t, f"""{nav_html(t, data, prof, 1)}
      <div class="page" style="--h2:{38 if len(p['title']) < 34 else 34}px"><div class="head"><div><span class="chip">{icon('flame', 14)}{esc(p['eyebrow'])}</span>
        <h2>{esc(p['title'])}</h2><p>{esc(p['sub'])}</p></div>
        <span class="btn dk lg2">{icon('sparkle', 15)}{esc(p['add'])}</span></div>
        <div class="cards">{cards}</div></div>""")


def page_bento(t, data, prof):
    p = prof["p3"]
    c1, c2 = p["cards"]
    tile = lambda c: (f'<div class="tile info"><div class="ico">{icon(c[0], 22)}</div><h3>{esc(c[1])}</h3><p>{esc(c[2])}</p>'
                      f'<span class="lab">{esc(c[3])}</span></div>')
    stars = "".join(icon("star", 14, fill=True) for _ in range(5))
    return shell_html(t, f"""{nav_html(t, data, prof, 2)}
      <div class="page"><div class="head c"><span class="eyebrow">{esc(p['eyebrow'])}</span><h2>{esc(p['title'])}</h2><p>{esc(p['sub'])}</p></div>
        <div class="bento">
          <div class="tile ph" style="grid-column:1/3"><img src="{esc(data['IMG_FINITION'])}">
            <div class="tx"><small>{esc(prof['p2']['eyebrow'])}</small><h3>{esc(data['TITLE_IMG_3'])}</h3><p>{esc(data['DESC_IMG_3'])}</p></div></div>
          {tile(c1)}
          <div class="tile quote"><div class="stars">{stars}</div><q>{esc(p['quote'])}</q><div class="who">{esc(p['who'])}<small>{esc(p['role'])}</small></div></div>
          {tile(c2)}
          <div class="tile ph" style="grid-column:2/5"><img src="{esc(data['IMG_ATELIER'])}" style="object-position:center 40%">
            <div class="tx"><small>{esc(p['caption'])}</small><h3>{esc(data['TITLE_IMG_4'])}</h3></div></div>
        </div></div>""")


def page_detail(t, data, prof):
    p = prof["p4"]
    tabs = "".join(f'<span class="{"on" if i == 0 else ""}">{esc(x)}</span>' for i, x in enumerate(p["tabs"]))
    rows = "".join(f'<div class="row"><div><h4>{esc(n)}<i>{esc(b)}</i></h4><p>{esc(d)}</p></div><span class="val">{esc(v)}</span></div>'
                   for n, b, d, v in p["items"])
    n0, b0, d0, v0 = p["items"][0]
    return shell_html(t, f"""{nav_html(t, data, prof, 3, glass=True)}
      <div class="page dark"><div class="head"><div><span class="eyebrow">{esc(p['eyebrow'])}</span><h2>{esc(p['title'])}</h2><p>{esc(p['sub'])}</p></div>
        <div class="tabs">{tabs}</div></div>
        <div class="panels">
          <div class="panel"><div class="ph-h"><span>{esc(p['head'][0])}</span><span>{esc(p['head'][1])}</span></div>{rows}
            <div class="pfoot"><span>{esc(p['foot_l'])}</span><b>{esc(p['foot_r'])}</b></div></div>
          <div class="panel feat"><div class="img"><img src="{esc(data['IMG_ATELIER'])}"><span>{esc(b0)}</span></div>
            <h3>{esc(data['TITLE_IMG_4'])}</h3><p>{esc(data['DESC_IMG_4'])}</p>
            <div class="pfoot"><span>{esc(p['head'][0])}</span><span class="go">{esc(p['cta'])}{icon('arrow', 14)}</span></div></div>
        </div></div>""")


def page_config(t, data, prof):
    c = prof["config"]
    stepper = '<span class="sep"></span>'.join(
        f'<div class="st {"done" if i < 1 else "on" if i == 1 else ""}"><i>{"✓" if i < 1 else i + 1}</i><span>{esc(n)}</span></div>'
        for i, n in enumerate(c["steps"]))
    opts = "".join(f'<div class="opt {"sel" if i == c["sel"] else ""}"><div class="ico">{icon(ic, 21)}</div>{esc(lb)}</div>'
                   for i, (ic, lb) in enumerate(c["opts"]))
    rows = "".join(f'<div class="tr"><span>{esc(a)}</span><b>{esc(b)}</b></div>' for a, b in c["ticket"])
    return shell_html(t, f"""{nav_html(t, data, prof, 3, glass=True)}
      <div class="page dark" style="--h2:{38 if len(c['title']) < 40 else 34}px"><div class="head"><div><span class="eyebrow">{esc(c['eyebrow'])}</span>
        <h2>{esc(c['title'])}</h2><p>{esc(c['sub'])}</p></div><div class="stepper">{stepper}</div></div>
        <div class="panels">
          <div class="panel wiz"><h3>{esc(c['q'])}</h3><p>{esc(c['qsub'])}</p><div class="opts">{opts}</div>
            <div class="wnav"><span class="back">← {esc(c['prev'])}</span><span class="btn lg2">{esc(c['next'])}{icon('arrow', 15)}</span></div></div>
          <div class="panel feat ticket"><div class="th"><h3>{esc(c['ticket_title'])}</h3><small>Nº 0428</small></div>{rows}
            <span class="bdg">{icon('check', 14)}{esc(c['badge'])}</span>
            <span class="btn lg2">{icon('arrow', 15)}{esc(c['cta'])}</span></div>
        </div></div>""")


def build_sites(t, data, prof):
    last = ("04_devis", page_config(t, data, prof)) if data.get("CONFIGURATEUR") else ("04_tarifs", page_detail(t, data, prof))
    return [("01_accueil", page_home(t, data, prof)), ("02_realisations", page_cards(t, data, prof)),
            ("03_savoir_faire", page_bento(t, data, prof)), last]


# ---------------------------------------------------------------------------
# 2) La maquette de présentation : navigateur + smartphone (inchangé dans l'esprit)
# ---------------------------------------------------------------------------
def mockup_shell(t: dict, data: dict, prof: dict, idx: int, total: int, site_html: str) -> str:
    base = mix(t["text"], "#000000", 0.5)
    glow = mix(t["accent"], base, 0.4)
    host = re.sub(r"^www\.", "", re.sub(r"^https?://", "", data.get("SOURCE_SITE_URL", "")).split("/")[0])
    domain = "www." + (host or re.sub(r"[^a-z0-9]", "", normalize(data["BRAND_NAME"])) + ".fr")
    src = htmllib.escape(site_html, quote=True)
    dots = "".join(f'<i class="{"on" if i == idx else ""}"></i>' for i in range(total))
    label = prof["nav"][idx] if idx < len(prof["nav"]) else ""
    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">
    <link href="{font_url(t['heading_font'], t['body_font'], 'Inter')}" rel="stylesheet">
    <style>
      * {{ margin:0; padding:0; box-sizing:border-box; }}
      body {{ width:1920px; height:1080px; overflow:hidden; position:relative; color:#fff; font-family:'{t['body_font']}', sans-serif;
              background: radial-gradient(1000px 760px at 80% 25%, {glow}dd, transparent 70%),
                          radial-gradient(800px 600px at 5% 100%, {mix(t['accent'], base, .55)}aa, transparent 70%),
                          linear-gradient(135deg, {base}, {mix(base, '#000000', .4)}); }}
      body::before {{ content:""; position:absolute; inset:0; opacity:.45;
                      background-image:radial-gradient(rgba(255,255,255,.09) 1.2px, transparent 1.3px); background-size:34px 34px; }}
      .top {{ position:absolute; top:40px; left:91px; right:91px; display:flex; justify-content:space-between; align-items:center; z-index:5; }}
      .id {{ display:flex; align-items:center; gap:16px; }}
      .id .lg {{ border-radius:14px; overflow:hidden; display:block; box-shadow:0 10px 24px -8px rgba(0,0,0,.6); }}
      .id .lg.mono {{ display:grid; place-items:center; font-family:'{t['heading_font']}'; font-weight:800; color:#fff;
                      background:linear-gradient(135deg,{t['accent']},{mix(t['accent'], '#000000', .35)}); }}
      .id small {{ display:block; font-size:12px; font-weight:700; letter-spacing:.24em; text-transform:uppercase; opacity:.6; margin-bottom:3px; }}
      .id b {{ font-family:'{t['heading_font']}'; font-size:26px; font-weight:700; }}
      .pill {{ font-size:13px; font-weight:700; letter-spacing:.14em; text-transform:uppercase; padding:10px 20px;
               border:1px solid rgba(255,255,255,.28); border-radius:999px; background:rgba(255,255,255,.08); }}
      .browser {{ position:absolute; left:91px; top:130px; width:1280px; height:804px; border-radius:16px; background:#e9e9ec; overflow:hidden;
                  box-shadow:0 70px 110px -30px rgba(0,0,0,.75), 0 0 0 1px rgba(255,255,255,.12); z-index:2; }}
      .bar {{ height:44px; background:linear-gradient(#f4f4f6,#e4e4e8); display:flex; align-items:center; gap:9px; padding:0 18px; border-bottom:1px solid #cfcfd4; }}
      .bar i {{ width:12px; height:12px; border-radius:50%; background:#ff5f57; }}
      .bar i:nth-child(2) {{ background:#febc2e; }} .bar i:nth-child(3) {{ background:#28c840; }}
      .url {{ margin:0 auto; transform:translateX(-30px); width:520px; height:26px; border-radius:8px; background:#fff; color:#666; font:500 13px/26px 'Inter',sans-serif; text-align:center; }}
      .browser iframe {{ display:block; width:1280px; height:760px; border:0; background:#fff; }}
      .phone {{ position:absolute; left:1411px; top:130px; width:418px; height:804px; border-radius:60px; padding:14px; background:#0c0c0e; z-index:4;
                box-shadow:0 70px 100px -25px rgba(0,0,0,.8), inset 0 0 0 2px #3a3a3f, 0 0 0 1px rgba(255,255,255,.15); }}
      .phone iframe {{ width:390px; height:776px; border:0; border-radius:46px; background:#fff; display:block; }}
      .phone::after {{ content:""; position:absolute; top:26px; left:50%; width:110px; height:30px; margin-left:-55px; border-radius:20px; background:#0c0c0e; }}
      .bottom {{ position:absolute; bottom:38px; left:91px; right:91px; display:flex; justify-content:space-between; align-items:center; font-size:13px; opacity:.75; z-index:5; }}
      .dots {{ display:flex; gap:8px; }} .dots i {{ width:26px; height:4px; border-radius:2px; background:rgba(255,255,255,.3); }} .dots i.on {{ background:#fff; width:46px; }}
    </style></head><body>
      <div class="top"><div class="id">{logo_html(t, data, 54)}<div><small>Proposition de maquette</small><b>{esc(data['BRAND_NAME'])}</b></div></div>
        <span class="pill">{idx + 1:02d} — {esc(label)}</span></div>
      <div class="browser"><div class="bar"><i></i><i></i><i></i><div class="url">🔒 {domain}</div></div><iframe srcdoc="{src}"></iframe></div>
      <div class="phone"><iframe srcdoc="{src}"></iframe></div>
      <div class="bottom"><span>Aperçu non contractuel — version ordinateur &amp; mobile</span><div class="dots">{dots}</div></div>
    </body></html>"""


async def render_from_file(config_file: str):
    with open(config_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Logo : "LOGO": "chemin/ou/url.png" dans prospect.json
    logo = (data.get("LOGO") or "").strip()
    if logo:
        data["_logo_url"] = format_image(logo)
        if not logo.startswith(("http://", "https://")) and os.path.exists(logo):
            data["_logo_path"] = logo

    for key in ("HERO_IMG", "IMG_REALISATION", "IMG_FINITION", "IMG_ATELIER"):
        data[key] = format_image(data.get(key, ""))
    data.setdefault("CITY", city_from_badge(data))

    theme = build_theme(data)
    prof = profile_for(theme, data)
    out_dir = data.get("OUTPUT_DIR") or re.sub(r"\.\w+$", "", data.get("OUTPUT_FILE", "mockup")) or "mockup"
    os.makedirs(out_dir, exist_ok=True)

    sites = build_sites(theme, data, prof)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        pg = await browser.new_page(viewport={"width": 1920, "height": 1080})
        for i, (name, site_html) in enumerate(sites):
            tmp = os.path.abspath(f"_tmp_{name}.html")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(mockup_shell(theme, data, prof, i, len(sites), site_html))
            await pg.goto(f"file://{tmp}", wait_until="networkidle")
            await pg.wait_for_timeout(1500)
            path = os.path.join(out_dir, f"{name}.png")
            await pg.screenshot(path=path)
            os.remove(tmp)
            print(f"Image générée : {path}")
        await browser.close()


def city_from_badge(data: dict) -> str:
    parts = re.split(r"\s[—–-]\s", data.get("BADGE_TEXT", ""))
    return parts[-1].strip() if len(parts) > 1 else ""


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="Fichier JSON d'entrée")
    args = parser.parse_args()
    asyncio.run(render_from_file(args.config))
