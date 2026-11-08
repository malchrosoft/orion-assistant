# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Compétence « commande » : répondre à une question sur l'ordinateur en écrivant une commande shell.

Le modèle local propose UNE commande de consultation ; elle n'est lancée qu'après quatre garde-fous :
1. liste blanche : chaque programme de la commande doit être un outil de lecture connu ;
2. filtre : ni redirection vers un fichier, ni sous-shell, ni outil réseau ou d'administration ;
3. accord de la personne, après qu'Orion a montré et lu la commande ;
4. exécution bornée : 10 s au plus, sortie tronquée, et sous macOS dans un bac à sable sans écriture
   ni réseau (sandbox-exec). Sous Linux et Windows (PowerShell), les filtres seuls protègent : Windows n'a pas
   de bac à sable simple, la liste blanche n'y accepte donc que des cmdlets de lecture (Get-…) et de mise en forme.
"""
import platform
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

LECTURE = {
    "ls", "du", "df", "find", "wc", "ps", "uptime", "uname", "sw_vers", "sysctl", "system_profiler", "stat",
    "file", "head", "tail", "grep", "egrep", "sort", "uniq", "awk", "cut", "tr", "date", "whoami", "id",
    "hostname", "pwd", "echo", "cat", "mdfind", "mdls", "diskutil", "pmset", "vm_stat", "ioreg", "top",
    "free", "lsblk", "lscpu", "nproc", "ipconfig", "ifconfig", "networksetup", "sed", "xargs", "basename",
    "dirname", "realpath", "printf", "nl", "column", "lsusb", "lspci", "hostinfo", "scutil", "defaults",
}
# sous-commandes autorisées pour les outils qui savent aussi modifier le système
SOUS_COMMANDES = {"diskutil": {"list", "info"}, "networksetup": {"-listallhardwareports", "-getairportnetwork",
                                                                 "-listallnetworkservices"},
                  "defaults": {"read"}, "scutil": {"--get"}, "ipconfig": {"getifaddr", "getpacket"},
                  "pmset": {"-g"}}
INTERDIT = re.compile(r"(>|`|\$\(|;|&&|\|\||&\s*$|\bsudo\b|\brm\b|\bmv\b|\bcp\b|\bdd\b|\bchmod\b|\bchown\b|"
                      r"\bkill\w*\b|\bcurl\b|\bwget\b|\bssh\b|\bscp\b|\bnc\b|\bosascript\b|\beval\b|\bexec\b|"
                      r"\b(?:ba|z|)sh\b|\bpython\d*\b|\bperl\b|\bruby\b|-delete\b|-exec\b|\bsed\s+-i|\btee\b|"
                      r"\bwrite\b|\blaunchctl\b|\bshutdown\b|\breboot\b|\bmkfs\b|system\s*\(|-execdir\b|-ok\b|"
                      # données personnelles sensibles : jamais lues, même en consultation
                      r"\.ssh\b|\.aws\b|\.gnupg\b|keychain|\.netrc|password|passwd|secret|token|cookies?\b)",
                     re.IGNORECASE)

# Windows : PowerShell, seulement des cmdlets qui lisent ou mettent en forme
LECTURE_POWERSHELL = {
    "get-childitem", "get-process", "get-ciminstance", "get-volume", "get-psdrive", "get-netipaddress",
    "get-netadapter", "get-computerinfo", "get-date", "get-item", "get-itemproperty", "get-service", "get-disk",
    "get-physicaldisk", "get-hotfix", "get-uptime", "get-culture", "get-timezone", "measure-object",
    "select-object", "sort-object", "where-object", "format-table", "format-list", "select-string",
    "group-object", "write-output", "ls", "dir", "gci", "gps", "ps", "select", "sort", "where",
    "measure", "ft", "fl", "?",
}
INTERDIT_POWERSHELL = re.compile(
    r"(>|;|&|`|\$\(|\b(?:set|remove|new|stop|start|restart|invoke|add|clear|rename|move|copy|out|export|import|"
    r"install|uninstall|enable|disable|register|unregister|suspend|resume|send|connect|update|write-host)-\w+|"
    r"\b(?:iex|iwr|irm|curl|wget|del|erase|rm|rmdir|rd|mv|cp|kill|shutdown|reg|net|netsh|schtasks|wmic|"
    r"powershell|pwsh|cmd|start|sc)\b|-command\b|-encodedcommand\b|\.ssh\b|password|secret|token|credential|"
    # appels de méthode (« $_.Delete() », « [System.IO.File]::Delete(…) ») : ils peuvent modifier n'importe quoi
    r"\.\w+\s*\(|\[[\w.]+\]\s*::|foreach-object|%)",
    re.IGNORECASE)

CONSIGNE = ("Tu écris UNE seule commande {shell} pour {systeme}, qui LIT des informations sans rien modifier, "
            "sans sudo, sans réseau, sans écrire de fichier. Réponds uniquement par la commande, sur une ligne, "
            "sans explication ni bloc de code. Si c'est impossible sans modifier quoi que ce soit, réponds : IMPOSSIBLE")
# Exemples donnés au modèle, par système : un petit modèle imite mieux qu'il n'invente
EXEMPLES = {
    "macOS": ["niveau de la batterie → pmset -g batt", "programmes qui consomment le plus → ps -Ao pcpu,comm -r | head -6",
              "adresse IP → ipconfig getifaddr en0", "depuis quand l'ordinateur est allumé → uptime",
              "espace disque → df -h /", "nombre de fichiers dans mes documents → ls -1 ~/Documents | wc -l"],
    "Linux": ["niveau de la batterie → cat /sys/class/power_supply/BAT0/capacity",
              "programmes qui consomment le plus → ps -eo pcpu,comm --sort=-pcpu | head -6",
              "adresse IP → hostname -I", "depuis quand l'ordinateur est allumé → uptime -p", "espace disque → df -h /"],
    "Windows": ["niveau de la batterie → Get-CimInstance Win32_Battery | Select-Object EstimatedChargeRemaining",
                "programmes qui consomment le plus → Get-Process | Sort-Object CPU -Descending | Select-Object -First 5 Name,CPU",
                "adresse IP → Get-NetIPAddress -AddressFamily IPv4 | Select-Object IPAddress",
                "espace disque → Get-Volume | Format-Table DriveLetter,SizeRemaining,Size"],
}
RESUME = ("Voici une question et la sortie brute d'une commande. Réponds à la question en une ou deux phrases "
          "simples, en français, en tutoyant, sans mise en forme, sans inventer ce qui n'est pas dans la sortie.")


def systeme():
    return {"Darwin": "macOS", "Linux": "Linux", "Windows": "Windows"}.get(platform.system())


def proposer(question, conversation):
    """Commande proposée par le modèle local, ou None."""
    if not systeme() or not conversation:
        return None
    shell = {"macOS": "zsh", "Linux": "bash", "Windows": "PowerShell"}[systeme()]
    consigne = CONSIGNE.format(shell=shell, systeme=systeme()) + "\nExemples :\n" + "\n".join(EXEMPLES[systeme()])
    sortie = conversation.completer(consigne, question, max_tokens=80)
    ligne = re.sub(r"^`+|`+$|^\$\s*", "", (sortie or "").strip().splitlines()[0] if sortie else "").strip()
    return None if not ligne or "IMPOSSIBLE" in ligne.upper() else ligne


def verifier(commande, pour=None):
    """(True, «») si la commande est une simple consultation autorisée, sinon (False, raison)."""
    if len(commande) > 300:
        return False, "la commande est trop longue"
    if (pour or systeme()) == "Windows":
        return _verifier_powershell(commande)
    if INTERDIT.search(commande):
        return False, "elle contient une opération interdite (écriture, réseau, administration ou sous-shell)"
    for morceau in commande.split("|"):
        try:
            mots = shlex.split(morceau)
        except ValueError:
            return False, "elle est mal formée"
        if not mots:
            return False, "elle est mal formée"
        programme = Path(mots[0]).name
        if programme not in LECTURE:
            return False, f"« {programme} » n'est pas dans la liste des outils de consultation"
        if programme in SOUS_COMMANDES and not (set(mots[1:2]) & SOUS_COMMANDES[programme]):
            return False, f"« {programme} » n'est permis qu'en consultation"
        if programme == "xargs":  # xargs lance un autre programme : il doit être lui aussi de consultation
            cible = next((m for m in mots[1:] if not m.startswith("-")), "")
            if Path(cible).name not in LECTURE:
                return False, f"« xargs {cible} » n'est pas une consultation"
        if programme == "top" and "-l" not in mots and "-n" not in mots:
            return False, "« top » doit s'arrêter seul (option -l ou -n)"
    return True, ""


def _verifier_powershell(commande):
    if INTERDIT_POWERSHELL.search(commande):
        return False, "elle contient une opération interdite (modification, réseau, administration ou sous-commande)"
    for morceau in commande.split("|"):
        mots = morceau.split()
        if not mots:
            return False, "elle est mal formée"
        if mots[0].lower() not in LECTURE_POWERSHELL:
            return False, f"« {mots[0]} » n'est pas dans la liste des commandes de consultation"
    return True, ""


def executer(commande, delai=10, limite=4000):
    """Lance la commande (déjà vérifiée) ; renvoie sa sortie (tronquée). Sous macOS : bac à sable sans
    écriture (sauf /dev et le dossier temporaire) ni réseau."""
    shell = (["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Restricted", "-Command", commande]
             if systeme() == "Windows" else ["/bin/zsh" if systeme() == "macOS" else "/bin/bash", "-c", commande])
    if systeme() == "macOS":
        profil = Path(tempfile.gettempdir()) / "orion-lecture.sb"
        profil.write_text('(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n'
                          '(allow file-write* (subpath "/dev") (subpath "/private/var/folders"))\n')
        shell = ["sandbox-exec", "-f", str(profil)] + shell
    try:
        r = subprocess.run(shell, capture_output=True, text=True, timeout=delai)
    except subprocess.TimeoutExpired:
        return "(la commande a dépassé le temps permis et a été arrêtée)"
    sortie = (r.stdout or r.stderr or "").strip()
    return sortie[:limite] + ("\n…" if len(sortie) > limite else "") if sortie else "(aucune sortie)"


def resumer(question, sortie, conversation):
    """Réponse courte à partir de la sortie ; sans modèle, la sortie elle-même (courte)."""
    if len(sortie) <= 160:  # sortie courte : on la donne telle quelle, un résumé risquerait d'inventer
        return "Résultat : " + " ".join(sortie.split())
    texte = conversation.completer(RESUME, f"Question : {question}\nSortie :\n{sortie[:2500]}",
                                   max_tokens=120) if conversation else None
    return re.sub(r"[*_`#]+", "", texte or sortie[:300]).strip()  # dit à voix haute : sans mise en forme
