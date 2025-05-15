# Better King
Burger King Coupon Telegram Bot

<html><img src="https://github.com/coffeerhyder/BKCouponCrawler/blob/GithubMirror/media/Logo2.jpeg?raw=true" width="220" height="216" /> </br>
<img src="https://github.com/coffeerhyder/BKCouponCrawler/blob/GithubMirror/media/2021_01_24_Showcase_2.png?raw=true" width="360" height="640" /> </br> </html>

# Features
* Alle Burger King Coupons ohne App & Accountzwang
* Crawler und Bot getrennt: Crawler kann einfach für andere Projekte verwendet werden
* Coupons sortiert, aufgeräumt und teils mit zusätzlichen Informationen
* Coupons einfach beliebig filterbar und sortierbar
* Demnächst erscheinende Coupons vorab einsehen

**Video:**  
https://www.bitchute.com/video/eoMYCfag5oiM/

# Live Instanz:
# [Zum TG Channel](https://t.me/BetterKingPublic) | [Ansicht ohne TG Account](https://t.me/s/BetterKingPublic)
# [Zum TG Bot](https://t.me/BetterKingBot)
# [Zur Matrix Bridge](https://app.element.io/#/room/#BetterKingDE:matrix.org)

# Installation
1. ``git clone https://github.com/coffeerhyder/BKCouponCrawler.git``
2. ``apt install python3-pip``
3. ``pip3 install -r requirements.txt``
4. [CouchDB](https://linuxize.com/post/how-to-install-couchdb-on-ubuntu-20-04/) installieren und einrichten.  
5. `config.json.default` in `config.json` umbenennen und eigene Daten eintragen (siehe unten).
6. Eine wichtige couchDB Einstellung festlegen:
``` max_document_id_number ``` --> Auf 1000 setzen siehe: https://docs.couchdb.org/en/latest/config/misc.html#purge
7. python 3.9 installieren siehe unten
8. `BKBot.py` einmalig mit dem Parameter `crawl` aufrufen, um das erstmalige Crawlen der Coupons zu erzwingen.

# Installation Python 3.9 mit VENV
1. Python 3.9 installieren: https://askubuntu.com/questions/1318846/how-do-i-install-python-3-9
2. Python 3.9 VENV installieren: `apt-get install python3.9-venv`
3. `sudo apt-get -y install git-all`
4. `sudo apt-get -y install pip`
5. `pip install virtualenv`
6. `git clone https://github.com/farOverNinethousand/WGTools`
7. `python3.9 -m venv venv`
8. `source venv/bin/activate`
9. `pip install -r requirements.txt`

# Verwendung
1. Den Bot mit der `bkstart.sh` starten.
2. Ggf Autostart in Crontab einrichten.

# CouchDB (user-DB) Backup & Wiederherstellen
Backup:
```
git clone https://github.com/danielebailo/couchdb-dump
-->
bash couchdb-dump.sh -b -H 127.0.0.1 -d telegram_users -f telegram_users.json -u username -p password
```
Wiederherstellen:
```
Alte DB löschen, da bestehende Einträge nicht überschrieben werden:
curl -X DELETE http://username:password@127.0.0.1:5984/telegram_users
Wiederherstellen des Backups:
bash couchdb-dump.sh -r -c -H 127.0.0.1 -d telegram_users -f telegram_users.json -u username -p password
```


# config.json (siehe config.json.default)
| Key                 | Datentyp    | Optional | Beschreibung                                                                                         | Beispiel                                 |
|---------------------|-------------|----------|------------------------------------------------------------------------------------------------------|------------------------------------------|
| bot_token           | String      | Nein     | Bot Token                                                                                            | `1234567890:HJDH-gh56urj6r5u6grhrkJO7Qw` |
| db_url              | String      | Nein     | URL zur CouchDB DB samt Zugangsdaten                                                                 | `http://username:pw@localhost:5984/`     |
| public_channel_name | String      | Ja       | Name des öffentlichen Telegram Channels, in den der Bot die aktuell gültigen Gutscheine posten soll. | `TestChannel`                            |
| bot_name            | String      | Nein     | Name des Bots                                                                                        | `BetterKingBot`                          |
| admin_ids           | StringArray | Nein     | Telegram UserIDs der gewünschten Bot Admins                                                          | ["57659679843", "534494657832"]          |

**Falls nur der Crawler benötigt wird, reicht die CouchDB URL (mit Zugangsdaten)!**

### Bot mit Logging in File starten
```
python3 BKBot.py 2>&1 | tee /tmp/bkbot.log
```

### Mögliche Start-Parameter für `BKBot.py`:  
Die meisten Parameter sind nur einzeln verwendbar.  

```
usage: BKBot.py [-h] [-fc FORCECHANNELUPDATEWITHRESEND]
                [-rc RESUMECHANNELUPDATE] [-fb FORCEBATCHPROCESS]
                [-un USERNOTIFY] [-n NUKECHANNEL] [-cc CLEANUPCHANNEL]
                [-m MIGRATE] [-c CRAWL] [-mm MAINTENANCEMODE]

optional arguments:
  -h, --help            show this help message and exit
  -fc FORCECHANNELUPDATEWITHRESEND, --forcechannelupdatewithresend FORCECHANNELUPDATEWITHRESEND
                        Sofortiges Channelupdates mit löschen- und neu
                        Einsenden aller Coupons.
  -rc RESUMECHANNELUPDATE, --resumechannelupdate RESUMECHANNELUPDATE
                        Channelupdate fortsetzen: Coupons ergänzen, die nicht
                        rausgeschickt wurden und Couponübersicht erneuern.
                        Nützlich um ein Channelupdate bei einem Abbruch genau
                        an derselben Stelle fortzusetzen.
  -fb FORCEBATCHPROCESS, --forcebatchprocess FORCEBATCHPROCESS
                        Alle Aktionen ausführen, die eigentlich nur täglich 1x
                        durchlaufen: Crawler, User Benachrichtigungen
                        rausschicken und Channelupdate mit Löschen- und neu
                        Einsenden.
  -un USERNOTIFY, --usernotify USERNOTIFY
                        User benachrichtigen über abgelaufene favorisierte
                        Coupons, die wieder zurück sind und neue Coupons (=
                        Coupons, die seit dem letzten DB Update neu hinzu
                        kamen).
  -n NUKECHANNEL, --nukechannel NUKECHANNEL
                        Alle Nachrichten im Channel automatisiert löschen
                        (debug/dev Funktion)
  -cc CLEANUPCHANNEL, --cleanupchannel CLEANUPCHANNEL
                        Zu löschende alte Coupon-Posts aus dem Channel
                        löschen.
  -m MIGRATE, --migrate MIGRATE
                        DB Migrationen ausführen falls verfügbar
  -c CRAWL, --crawl CRAWL
                        Crawler beim Start des Bots einmalig ausführen.
  -mm MAINTENANCEMODE, --maintenancemode MAINTENANCEMODE
                        Wartungsmodus - zeigt im Bot und Channel eine
                        entsprechende Meldung. Deaktiviert alle Bot
                        Funktionen.
```

### Bot mit Systemstart starten (Linux)
1. Sichergehen, dass BKBot.py ausführbar ist. Falls nötig: ``chmod a+b BKBot.py``.
2. Per ``crontab -e`` in crontab wechseln.
3. Folgendes hinzufügen:  
```
# Bot Start Script alle X Minuten ausführen um sicherzugehen, dass der Bot immer läuft
*/1 * * * * sh /root/betterking/BKCouponCrawler/bkstart.sh

# Optionale Commands: Updates nachts automatisch ausführen
00 03 * * * root /usr/bin/apt update -q -y >> /var/log/apt/automaticupdates.log
30 03 * * * root /usr/bin/apt upgrade -q -y >> /var/log/apt/automaticupdates.log
# Jede Nacht um 4 Uhr neustarten
00 04 * * * reboot
```
4. Falls gewollt, Bot beenden mit ``pkill python3`` (vereinfachte Variante).

### Interne Coupon-Typen und Beschreibung
|ID | Interne Bezeichnung | Beschreibung|
--- | --- | --- | 
|0 | APP | App Coupons|
|3 | PAPER | Papiercoupons|
|4 | PAPER_UNSAFE | Coupons aus der "Coupons2" API, die keinem anderen Coupon-Typen zugewiesen werden konnten.|
|5 | ONLINE_ONLY | Coupons ohne short PLU Code, die wenn überhaupt nur online oder per QR Code (Terminal) bestellbar sind.|
|6 | ONLINE_ONLY_STORE_SPECIFIC | Coupons, die nur in bestimmten Filialen einlösbar sind -> Derzeit ist das nur ein Platzhalter|
|7 | SPECIAL | Spezielle Coupons, die manuell über die ``config_extra_coupons.json`` eingefügt werden können.|
|8 | PAYBACK | Payback Papiercoupons, die manuell über die ``config_extra_coupons.json`` eingefügt werden können.|

# TODOs
* Crawler jede Stunde laufen lassen und Channel aktualisieren, sobald es neue Coupons gibt (+ erzwungenermaßen 1x am Tag)
* Zeitberechnungen refactoring: timedelta überall verwenden wo möglich
* MessageHandler für nicht unterstützte Kommandos/Text einbauen
* Handling mit Datumsangaben prüfen/verbessern
* couchdb-dump updaten, sodass es per Parameter beim restore die DB wahlweise vorher löschen- und neu erstellen oder Items überschreiben kann
* Channelupdate "fortsetzen" nach Abbruch ermöglichen --> Autom. Neuversuch bei Netzwerkfehlern o.ä.

# Daten für den BotFather (Telegram Bot Konfiguration)

### Bot Commands Liste
```
start - Hauptmenü
coupons - Alle Coupons
coupons2 - Coupons ohne Menü
favoriten - ⭐Favoriten⭐
angebote - Angebote
payback - 🅿️ayback Karte
einstellungen - 🔧Einstellungen
stats - Statistiken für Nerds
tschau - 🚫 Meinen Account löschen
 ```

### [Vorlage] Bot About
```
Burger King Coupons auf Telegram
Made with ❤ and 🍻 during 😷
Channel: @BetterKingPublic
Kontakt: bkfeedback@pm.me
```

### [Vorlage] Bot Description
```
Burger King Coupons auf Telegram
- Channel: @BetterKingPublic
- Kontakt: bkfeedback@pm.me
Features:
- Alle BK Coupons immer aktuell (auch Papiercoupons)
- MyBK Coupons ohne Account und unendlich oft einlösbar
- Datensparsam & superschnell
- Favoriten speichern & optionale Benachrichtigung bei Wiederverfügbarkeit
- Kein Tracking
- Offline verwendbar (sofern Bilder vorher geladen wurden)
- Open source: github.com/coffeerhyder/BKCouponCrawler
Made with ❤ and 🍻 during 😷
```

### [Vorlage] Channel Description
```
Burger King Coupons auf Telegram est. 2020
Made with ❤ and 🍻 during 😷
Zum Bot: @BetterKingBot
Kontakt: bkfeedback@pm.me
Quellcode: github.com/coffeerhyder/BKCouponCrawler
```

### [Vorlage] Channel angepinnter Post mit Papiercoupons Datei & Verlinkung
```
Aktuelle Papiercoupons (gültig bis 24.09.2021):
Externer Downloadlink: mega.nz/folder/zWQkRIoD#-XRxtHFcyJZcgvOKx4gpZg
Quelle(n):
mydealz.de/gutscheine/burger-king-coupons-bundesweit-gultig-bis-23042021-1762251
mydealz.de/gutscheine/burger-king-coupons-bundesweit-gultig-bis-05032021-1731958
```

### [Vorlage] Channel angepinnter Post mit Papiercoupons nur Verlinkung (neue Variante ohne extra Upload der Datei)
```
Aktuelle Papiercoupons (gültig bis 24.09.2021):
mydealz.de/gutscheine/burger-king-papier-coupons-bis-2409-1840299
```

### Channel FAQ
```
FAQ BetterKing Bot und Channel

Wo finde ich die aktuellen Papiercoupons als Scan?
Hier:
mega.nz/folder/zWQkRIoD#-XRxtHFcyJZcgvOKx4gpZg
Dieser Ordner dient außerdem als Archiv.

Welche Daten speichert der Bot?
Deine Benutzer-ID, deine Einstellungen und alle 48 Stunden einen Zeitstempel der letzten Bot verwendung.
Diese Daten werden nicht ausgewertet und du kannst sie jederzeit mit dem Befehl '/tschau' endgültig aus der Datenbank löschen.
Der Zeitstempel dient nur dazu, inaktive Accounts nach 6 Monaten automatisch löschen zu können.

Kann der Bot meine Telefonnummer sehen?
Nein das können Bots standardmäßig nur, wenn du es erlaubst.
Selbst wenn du dies tust: Der Bot speichert ausschließlich die oben genannten Daten.

Wie kann ich (Papier-)Coupons am Terminal einlösen?
Seit der Einführung des MyBK Prämienprogramms ist das etwas schwer zu finden:
Bei dem Punkt, an dem du deinen "mybk Logincode" eingeben kannst, kannst du auch einfach Papiercoupons eintippen.
Wichtig ist, dass du dort entweder den QR Code zeigst oder den langen Code eintippst, nicht den dreistelligen kurzern Code.

Meine BK Filiale verlangt original Papier-/App Coupons, wie kann ich die aus dem Channel dennoch verwenden?
Es gibt mehrere Möglichkeiten:
- Versuche, die Kurz-Codes einfach anzusagen
- Fahre durch den Drive hier werden idR. alle genommen
- Falls deine BK Filiale die Vorbestellen Funktion bietet, scanne die Coupons im Bestellvorgang mit deinem Handy (Zweitgerät/Laptop benötigt)

Wo finde ich den Quellcode?
Hier: github.com/coffeerhyder/BKCouponCrawler

Wie kann ich Fehler melden oder Feedback einreichen?
Per Mail: bkfeedback@pm.me

Gibt es ähnliche Projekte für BK?
Nein

Gibt es sowas auch für McDonalds/KFC/...?
McDonald's
01. mcbroken.com | Wo funktioniert die Eismaschine?
Sonstige
01. billigepizza.netlify.app | Pizzapreise bei Domino's optimieren
—> Video
 (https://www.youtube.com/watch?v=rChjUHveYxI)  
02. mistersnax.com | Lieferando in geiler z.B. Gruppenbestellungen, Preisvergleich

Linksammlung BK:
01. burgerking.de/sparkings | Spar Kings
02. burgerking.de/kingdeals | KING Deals
03. burgerking.de/rewards/offers | Coupons Webansicht
04. burgerking.de/store-locator | KING Finder
05. ngb.to/threads/betterking-burger-king-coupons-telegram-bot.110780/
06. pr0gramm.com/user/FishEater23/uploads/4730464
07. plus.rtl.de/video-tv/shows/team-wallraff-reporter-undercover-242031
08. reddit.com/r/de/comments/1jbi8iw/ich_habe_hier_mal_die_preise_bei_meinem_lokalen/
```

### Test Cases
* Alle Coupon Kategorien
* User Favoriten
* User mit Favoriten + abgelaufenen Favoriten
* Einstellungen
* Channel Renew
* Test mit neuem User

### BK Feedback Codes Recherche
Feedback Codes sind ...
* Hier generierbar: https://www.bk-feedback-de.com/
* 8-stellig: Zwei großgeschriebene Anfangsbuchstaben (variieren je nach Monat) und 6 Zahlen z.B. `BB123456`
* Offiziell gültig bei Abgabe eines maximal 30 Tage alten Kassenbons

Tabelle: Buchstabencodes für alle Monate:
  
| Monat     | Code |
|-----------|------|
| Januar    | BB   |
| Februar   | LS   |
| März      | JH   |
| April     | PL   |
| Mail      | BK   |
| Juni      | WH   |
| Juli      | FF   |
| August    | BF   |
| September | CF   |
| Oktober   | CK   |
| November  | CB   |
| Dezember  | VM   |

### Danke an
* https://github.com/3dik/bkoder
* https://edik.ch/posts/hack-the-burger-king.html
* https://www.mydealz.de/gutscheine/burger-king-bk-plu-code-sammlung-uber-270-bkplucs-822614
* https://limits.tginfo.me/de-DE
* https://www.mydealz.de/profile/jokergermany
* Alle MyDealz User, die die neuen Papiercoupons posten

### Kleine Linksammlung
* https://www.mydealz.de/diskussion/burger-king-gutschein-api-1741838
* https://www.burgerking.de/rewards/offers (Coupons direkt über die BK Webseite)
* https://pr0gramm.com/user/FishEater23/uploads/4730464
* https://ngb.to/threads/betterking-burger-king-coupons-telegram-bot.110780/
* https://github.com/reteps/burger-king-api-wrapper
* https://github.com/robsonkades/clone-burger-king-app-with-expo
* https://www.mccoupon.deals/ | [Autor](https://www.mydealz.de/profile/Jicu) | [Quelle](https://www.mydealz.de/gutscheine/burger-king-gutscheine-mit-plant-based-angeboten-1979906?page=3#comment-36031037)
* https://mcbroken.com/
* https://www.reddit.com/r/de/comments/1jbi8iw/ich_habe_hier_mal_die_preise_bei_meinem_lokalen/

### Ähnliche Projekte | funktionierend
Name | Beschreibung | Live-Instanz
--- | --- | ---
Generisches BK Projekt | https://github.com/reteps/burger-king-api-wrapper | -
Generisches BK Projekt | https://github.com/robsonkades/clone-burger-king-app-with-expo | -
billigepizza.netlify.app | Pizzapreise von Domino's optimieren | https://billigepizza.netlify.app/
MisterSnax (ehemals Spätzlehunter) | Lieferando in geiler z.B. Gruppenbestellungen, Preisvergleich | https://mistersnax.com/



### Ähnliche Projekte | down/defekt
Name | Beschreibung                                                                                                                                                    | Live-Instanz                                                                          | Down/Kaputt seit
--- |-----------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------| ---
freecokebot aka gimmecockbot | McDonalds gratis Getränke                                                                                                                                       | https://t.me/gimmecockbot (Alternativ https://t.me/freecokebot)                       | 10.11.2022
bk.eris.cc | BK Coupons ohne App, [Autor](https://gist.github.com/printfuck)                                                                                                 | https://bk.eris.cc/                                                                   | 10.11.2022
mcdonalds4free_bot | McDonalds Getränke kostenlos, [MyDealz Thread](https://www.mydealz.de/diskussion/mcdonalds-hasst-diesen-trick-freigetranke-free-softdrink-coffee-small-1550092) | https://t.me/mcdonalds4free_bot                                                       | 15.01.2023
Würger King | Burger King Coupons                                                                                                                                             | https://wurgerking.wfr.moe/  ([Quellcode](https://github.com/WebFreak001/WurgerKing)) | 31.12.2022
NordseeCoupons | Nordsee Coupons Bot                                                                                                                                             | https://t.me/NordseeCouponsBot und https://t.me/nordseecoupons     | 23.11.2023
Mccoupon | Mcdonalds Coupons                                                                                                                                               | https://www.mccoupon.deals/    | 25.11.2023


#### Ideen für ähnliche Projekte
* Couponplatz Crawler/Bot (aber auch einfach nur, um sie zu ärgern lol)
* KFC Bot
* Nordsee Bot