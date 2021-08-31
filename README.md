# Better King
Burger King Coupon Telegram Bot

<html><img src="https://www.picflash.org/viewer.php?img=Logo36AUIGS.jpg" width="220" height="216" /> </br>
<img src="https://www.picflash.org/viewer.php?img=2021_01_24_Showcase_21OL5XA.png" width="360" height="640" /> </br> </html>

**Video:**  
https://www.bitchute.com/video/eoMYCfag5oiM/

# Live Instanz:
# [Zum TG Channel](https://t.me/BetterKingPublic) | [Ansicht ohne TG Account](https://t.me/s/BetterKingPublic)
# [Zum TG Bot](https://t.me/BetterKingBot)
# [Zur Matrix Bridge](https://app.element.io/#/room/#BetterKingDE:matrix.org)

# Installation
1. ``git clone https://github.com/BetterKingBot/bkcouponcrawler/bkcouponcrawler.git``
2. ``apt install python3-pip``
3. ``pip3 install -r requirements.txt``
4. [CouchDB](https://linuxize.com/post/how-to-install-couchdb-on-ubuntu-20-04/) installieren und einrichten.  
5. `config.json.default` in `config.json` umbenennen und eigene Daten eintragen (siehe unten).
6. Eine wichtige couchDB Einstellung festlegen:
``` max_document_id_number ``` --> Auf 1000 setzen siehe: https://docs.couchdb.org/en/latest/config/misc.html#purge
7. `Crawler.py` einmalig durchlaufen lassen.  
8. `BKBot.py` starten.


# config.json (siehe config.json.default)
Key | Datentyp | Optional | Beschreibung | Beispiel
--- | --- | --- | --- | ---
bot_token | String | Nein | Bot Token | `1234567890:HJDH-gh56urj6r5u6grhrkJO7Qw`
db_url | String | Nein | URL zur CouchDB DB samt Zugangsdaten | `http://username:pw@localhost:5984/` 
public_channel_name | String | Ja | Name des öffentlichen Telegram Channels, in den der Bot die aktuell gültigen Gutscheine posten soll.  | `TestChannel`
bot_name | String | Nein | Name des Bots | `BetterKingBot`
**Falls nur der Crawler benötigt wird, reicht die CouchDB URL (mit Zugangsdaten)!**

## config_paper_coupons.json: Optionale Config zur Erkennung von Papiercoupons
Die `config_paper_coupons.json` wie folgt befüllen:  
Gäbe es derzeit z.B. Papiercoupons mit dem Buchstaben ``B`` und Ablaufdatum  ``05.03.2021`` **und** ``C`` mit dem Ablaufdatum ``23.04.2021``, müsste die json Datei wie folgt angepasst werden:
   
```
{
{
  "B": {
    "expire_date": "2021-03-05"
  },
  "C": {
    "expire_date": "2021-04-23"
  }
}
}   
```  
**Achtung: Ist diese Datei nicht auf dem aktuellen Stand, werden Papiercoupons nicht unbedingt als solche erkannt bzw. mit einem dummy Ablaufdatum gekennzeichnet!**

## config_special_coupons.json: Optionale Config zum manuellen Hinzufügen sogenannter "special Coupons"
Die ``config_special_coupons.json`` ist nützlich, um manuell Coupons hinzuzufügen, die in keiner der BK Datenbanken enthalten sind z.B. [solche](https://www.mydealz.de/gutscheine/gratis-eis-und-softdrink-bei-burger-king-1804058).
Beispiel:  
```
Siehe config_special_coupons.json
```  

### Mögliche Start-Parameter für `BKBot.py`:  

Parameter | Beschreibung
--- | ---
forcechannelupdate | Sofortiges Channelupdate
forcechannelupdatewithresend | Sofortiges Channelupdates mit löschen- und neu Einsenden aller Coupons.
resumechannelupdate | Channelupdate fortsetzen: Coupons ergänzen, die nicht rausgeschickt wurden und Couponübersicht erneuern. Nützlich um ein Channelupdate bei einem Abbruch genau an derselben Stelle fortzusetzen.
forcebatchprocess | Alle drei Aktionen ausführen, die eigentlich nur täglich 1x durchlaufen: Crawler, User Favoriten Benachrichtigungen rausschicken und Channelupdate mit Löschen- und neu Einsenden.
usernotify | User benachrichtigen über abgelaufene favorisierte Coupons, die wieder zurück sind und neue Coupons (= Coupons, die seit dem letzten DB Update neu hinzu kamen).
nukechannel | Alle Nachrichten im Channel automatisiert löschen (debug/dev Funktion für alle die zu faul sind, das von Hand zu tun ;) )
cleanupchannel | Zu löschende alte Coupon-Posts aus dem Channel löschen
migrate | DB Migrationen ausführen falls verfügbar
crawl | Crawler beim Start des Bots einmalig ausführen

### Interne Coupon-Typen und Beschreibung
ID | Interne Bezeichnung | Beschreibung
--- | --- | --- | 
0 | APP | App Coupons
1 | APP_VALID_AFTER_DELETION | App Coupons, die laut Ablaufdatum noch gültig sein müssten aber bereits nicht mehr per App-API zurückgegeben werden.
2 | APP_SAME_CHAR_AS_CURRENT_APP_COUPONS | Coupons mit denselben Abfangsbuchstaben wie aktuelle App Coupons, die jedoch nicht in der App API sind -> Potentielle "Special App Coupons"
3 | PAPER | Papiercoupons
4 | PAPER_UNSAFE | Coupons aus der "Coupons2" API, die keinem anderen Coupon-Typen zugewiesen werden konnten.
5 | ONLINE_ONLY | Coupons ohne short PLU Code, die wenn überhaupt nur online oder per QR Code (Terminal) bestellbar sind.
6 | ONLINE_ONLY_STORE_SPECIFIC | Coupons, die nur in bestimmten Filialen einlösbar sind -> Derzeit ist das nur ein Platzhalter
7 | SPECIAL | Spezielle Coupons, die manuell über die ``config_special_coupons.json`` eingefügt werden können.

# TODOs
* resumechannelupdate verbessern
* Channelupdate "fortsetzen" nach Abbruch ermöglichen --> Autom. Neuversuch bei "NetworkError"
* Feedback Codes / Gratis Kaffee einbauen
* User, die den Bot geblockt haben keine Benachrichtigungen mehr versuchen zu schicken (könnte passieren, wenn ein User Favoriten speichert. Benachrichtigungen aktiviert und dannach den Bot blockiert, TG Exception Unauthorized)
* Herausfinden, ob "Store-spezifische Coupons" offline vor Ort doch in allen Stores gehen oder die Akzeptanz gleich der der App ist
* App DB per Proxy in der originalen BK App modifizieren?
* App Coupons testen, die gerade nicht in der App sind aber noch gültig sein müssten

# Feature Ideen
* Bot: "Erweiterte Couponliste": Ähnliche Coupon-Liste wie im Channel, jedoch mit ausgeschriebenen Produktnamen
* PayBack Aktionen integrieren? https://www.mydealz.de/deals/20-fach-payback-punkte-coupon-bei-burger-king-1709510 --> Schwierig bis unmöglich zu automatisieren
* Einstellung, um abgelaufene Favoriten automatisch löschen zu lassen (sonst werden es ggf. über die Zeit immer mehr)

# Daten für den BotFather (Telegram Bot Konfiguration)

### Bot Commands Liste (in Verwendung)
```
start - Hauptmenü
tschau - 🚫 Meine Daten löschen
 ```

### Bot About
```
Made with ❤ and 🍻 during 😷
News-Channel & alle aktuellen Coupons: @BetterKingPublic
Feedback/Support: bkfeedback@pm.me
```

### Bot Description
```
Hilft beim Zunehmen ;)
- News-Channel & alle aktuellen Coupons: @BetterKingPublic
- Feedback & Support: bkfeedback@pm.me
Features:
- Alle BK Coupons immer aktuell (auch Papiercoupons)
- MyBK Coupons ohne Account und unendlich oft einlösbar
- Datensparsam & superschnell
- Favoriten speichern & optionale Benachrichtigung bei Wiederverfügbarkeit
- Kein Tracking
- Offline verwendbar (sofern Bilder vorher geladen wurden)
```

### Channel Description
```
Made with ❤ and 🍻 during 😷
Zum Bot: @BetterKingBot
Feedback/Support: bkfeedback@pm.me
```

### Channel angepinnter Post mit Papiercoupons Datei & Verlinkung
```
Aktuelle Papiercoupons (gültig bis 24.09.2021):
Externer Downloadlink: mega.nz/folder/HLJFGAyL#Da7bq1Sues_mrC-uvVLTGQ
Quelle(n):
mydealz.de/gutscheine/burger-king-coupons-bundesweit-gultig-bis-23042021-1762251
mydealz.de/gutscheine/burger-king-coupons-bundesweit-gultig-bis-05032021-1731958
```

### Channel angepinnter Post mit Papiercoupons nur Verlinkung (neue Variante ohne extra Upload der Datei)
```
Aktuelle Papiercoupons (gültig bis 24.09.2021):
mydealz.de/gutscheine/burger-king-papier-coupons-bis-2409-1840299
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
  
Monat | Code
--- | ---
Januar | BB
Februar | LS
März | JH
April | PL
Mail | BK
Juni | WH
Juli | FF
August | BF
September | CF
Oktober | CK
November | CB
Dezember | VM

### Online Vorbestellung Recherche
Über die BK App kann man in einigen Filialen [online vorbestellen](https://www.bundesverband-systemgastronomie.de/de/bdsnachricht/schnell-einfach-flexibel-bestellen-abholen-bei-burger-king-r.html).  
Hier lassen sich in der App die App Gutscheine auswählen, aber auch QR Codes scannen.
* Es sind alle PLUs bestellbar, auch laut Datum abgelaufene --> Vermutlich alles, was zu einem Produkt führt, das aktuell einen `availability_type` von `available` hat.
* Es befinden sich fast alle App- UND Papiercoupons im "Filial-spezifischen" Endpoint: `mo.burgerking-app.eu/api/v2/stores/123456/menu`
* Unterschiedliche Filialen können einen unterschiedlichen Pool von Coupons akzeptieren, aber die meisten Coupons funktionieren in allen Filialen
* Die online aufgelisteten Gutscheine sind nicht alle, die akzeptiert werden: beispielsweise können aktuell gültige Papiercoupons teilweise fehlen, obwohl Restaurants Papiercoupons generell akzeptieren -> Bedeutet im Klartext: Manche Papiercoupons lassen sich bei manchen Restaurants nicht in der online Vorbestellung nutzen, obwohl sie offline in der Filiale funktionieren müssten -> Fehler in der BK DB?! -> Ergibt einfach keinen Sinn

### Danke an
* [bkoder Projekt](https://github.com/3dik/bkoder)
* [Blog Artikel 'Hack the Burger King'](https://edik.ch/posts/hack-the-burger-king.html)
* [MyDealz BK PLU Sammlung](https://www.mydealz.de/gutscheine/burger-king-bk-plu-code-sammlung-uber-270-bkplucs-822614)
* https://limits.tginfo.me/de-DE

### Kleine Linksammlung
* https://www.mydealz.de/diskussion/burger-king-gutschein-api-1741838
* http://www.fastfood-forum.net/wbb3/upload/index.php/Board/9-Burger-King/

### Ähnliche BK Projekte auf GitHub (teilweise veraltet)
* https://github.com/WebFreak001/WurgerKing | [Live Instanz](https://wurgerking.wfr.moe/)
* https://github.com/reteps/burger-king-api-wrapper
* https://github.com/robsonkades/clone-burger-king-app-with-expo
* https://bk.eris.cc/ --> https://gist.github.com/printfuck

#### Ideen für ähnliche Projekte
* Couponplatz Crawler/Bot
* KFC Bot
* Aral Bot/Channel ([MeinAral App](https://mein.aral.de/service-tools/meinaral-app/))
* Payback Channel