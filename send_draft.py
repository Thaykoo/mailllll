import argparse
import glob
from html import escape as esc
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from generate_email import build_email_content

ENV_FILE = ".env"


def load_env(path: str = ENV_FILE):
    """Lit .env (KEY=VALUE) sans dépendance ; les variables d'environnement gardent la priorité."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_attachments(data: dict) -> list[str]:
    target = os.path.abspath(data.get("OUTPUT_DIR") or data.get("OUTPUT_FILE", "maquette"))
    folder = re.sub(r"\.\w+$", "", target)
    if os.path.isdir(folder):
        return sorted(glob.glob(os.path.join(folder, "*.png")))
    return [target] if os.path.isfile(target) else []


LOGO_PATH = os.path.join("signature", "logo_signature.png")
LOGO_CID = "onyxbuild-logo"


def signature_html(with_logo: bool) -> str:
    name = esc(os.environ.get("SENDER_NAME", "Prénom Nom"))
    title = esc(os.environ.get("SENDER_TITLE", "Développeur Web & Logiciel"))
    phone = esc(os.environ.get("SENDER_PHONE", ""))
    mail = esc(os.environ.get("MAIL_ADDRESS", ""))
    site = esc(os.environ.get("SENDER_SITE", mail.split("@")[-1] if "@" in mail else ""))
    ink = "#1e293b"  # même couleur que le corps du mail
    link = f"color:{ink};text-decoration:none"
    line = lambda v: f'<div style="font-size:14px;line-height:22px;color:{ink}">{v}</div>'
    info = ""
    if phone:
        info += line(f'<a href="tel:{phone.replace(" ", "")}" style="{link}">{phone}</a>')
    if mail:
        info += line(f'<a href="mailto:{mail}" style="{link}">{mail}</a>')
    if site:
        info += line(f'<a href="https://{site}" style="{link};font-weight:700">{site}</a>')
    logo = (f'<div style="margin:14px 0 12px"><img src="cid:{LOGO_CID}" width="200" alt="OnyxBuild" '
            'style="display:block;width:200px;height:auto;border:0"></div>') if with_logo else '<div style="height:12px"></div>'
    return f"""<div style="margin-top:28px;font-family:Helvetica,Arial,sans-serif">
  <div style="font-size:16px;line-height:22px;font-weight:700;color:{ink}">{name}</div>
  <div style="font-size:14px;line-height:22px;color:#64748b">{title}</div>
  {logo}
  {info}
</div>"""


def signature_text() -> str:
    lines = [os.environ.get("SENDER_NAME", "Prénom Nom"), os.environ.get("SENDER_TITLE", "Développeur Web & Logiciel")]
    for key in ("SENDER_PHONE", "MAIL_ADDRESS"):
        if os.environ.get(key):
            lines.append(os.environ[key])
    return "\n".join(lines)


def apply_signature(plain: str, html: str, with_logo: bool) -> tuple[str, str]:
    html = re.sub(r'<div class="signature">.*?</div>',
                  lambda _: signature_html(with_logo), html, flags=re.S)
    plain = re.sub(r"\[Votre Prénom\] \[Votre Nom\]\n.*\n\[Votre Téléphone\]",
                   lambda _: signature_text(), plain)
    return plain, html


def build_message(data: dict, sender: str, attachments: list[str]) -> EmailMessage:
    subject, plain, html, _ = build_email_content(data)
    with_logo = os.path.isfile(LOGO_PATH)
    plain, html = apply_signature(plain, html, with_logo)

    msg = EmailMessage()
    msg["From"] = f"{os.environ['SENDER_NAME']} <{sender}>" if os.environ.get("SENDER_NAME") else sender
    msg["To"] = data.get("EMAIL", "")
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")
    if with_logo:  # logo intégré dans le corps (CID), pas en pièce jointe visible
        with open(LOGO_PATH, "rb") as f:
            msg.get_body(("html",)).add_related(f.read(), "image", "png", cid=f"<{LOGO_CID}>")
    for path in attachments:
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        with open(path, "rb") as f:
            msg.add_attachment(f.read(), maintype=maintype, subtype=subtype, filename=os.path.basename(path))
    return msg


def open_in_thunderbird(msg: EmailMessage):
    """Écrit un .eml marqué « non envoyé » : Thunderbird l'ouvre en fenêtre de rédaction (HTML + pièces jointes)."""
    del msg["Date"], msg["Message-ID"]
    msg["X-Unsent"] = "1"
    path = os.path.abspath("brouillon_prospect.eml")
    with open(path, "wb") as f:
        f.write(msg.as_bytes())
    subprocess.Popen(["thunderbird", "-file", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description="Ouvre le mail du prospect dans Thunderbird, prêt à envoyer")
    parser.add_argument("config", help="Fichier JSON du prospect")
    parser.add_argument("--dry-run", action="store_true", help="Ne se connecte pas : écrit apercu_email.eml")
    args = parser.parse_args()

    load_env()
    with open(args.config, encoding="utf-8") as f:
        data = json.load(f)

    if not data.get("EMAIL"):
        sys.exit("[Erreur] Pas de champ EMAIL dans le JSON du prospect.")
    attachments = get_attachments(data)
    if not attachments:
        sys.exit("[Erreur] Aucune image trouvée : lance d'abord generate_mockup.py.")

    user = os.environ.get("MAIL_ADDRESS", "")
    msg = build_message(data, user or "moi@example.com", attachments)

    print(f"À        : {msg['To']}\nObjet    : {msg['Subject']}\nPièces jointes ({len(attachments)}) :")
    for a in attachments:
        print(f"  - {os.path.basename(a)}")

    if os.environ.get("SENDER_NAME", "Prénom Nom") == "Prénom Nom":
        print("\n[Attention] SENDER_NAME n'est pas renseigné dans .env : la signature affichera « Prénom Nom ».")

    if args.dry_run:
        with open("apercu_email.eml", "wb") as f:
            f.write(msg.as_bytes())
        print("\n[OK] Simulation : apercu_email.eml écrit.")
    elif shutil.which("thunderbird"):
        open_in_thunderbird(msg)
        print("\n[OK] Fenêtre Thunderbird ouverte : relis, puis clique sur Envoyer.")
    else:
        sys.exit("[Erreur] Thunderbird introuvable : sudo apt install thunderbird")


if __name__ == "__main__":
    main()
