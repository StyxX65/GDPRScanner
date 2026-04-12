# GDPR Scanner — Brugermanual

Version 1.6.15

---

## Indholdsfortegnelse

1. [Hvad er GDPR Scanner?](#1-hvad-er-gdpr-scanner)
2. [Overblik over brugerfladen](#2-overblik-over-brugerfladen)
3. [Forbindelse til dine datakilder](#3-forbindelse-til-dine-datakilder)
4. [Kør en scanning](#4-kør-en-scanning)
5. [Forstå resultaterne](#5-forstå-resultaterne)
6. [Gennemgang og mærkning af fund](#6-gennemgang-og-mærkning-af-fund)
7. [Sletning af elementer](#7-sletning-af-elementer)
8. [Profiler — gem dine scanningsindstillinger](#8-profiler--gem-dine-scanningsindstillinger)
9. [Rapporter og eksport](#9-rapporter-og-eksport)
10. [Del resultater med en gennemganger](#10-del-resultater-med-en-gennemganger)
11. [Planlagte scanninger](#11-planlagte-scanninger)
12. [E-mailrapporter](#12-e-mailrapporter)
13. [Sikkerhedskopi og gendannelse af database](#13-sikkerhedskopi-og-gendannelse-af-database)
14. [Indstillinger — oversigt](#14-indstillinger--oversigt)
15. [Ofte stillede spørgsmål](#15-ofte-stillede-spørgsmål)

---

## 1. Hvad er GDPR Scanner?

GDPR Scanner søger i din organisations digitale data — e-mails, cloud-filer, delte drev og lokale filservere — efter personoplysninger som CPR-numre, navne, adresser, telefonnumre og særlige kategorier af oplysninger efter GDPR artikel 9.

Når der er fundet elementer, kan du gennemgå dem, beslutte hvad der skal ske med hvert enkelt (beholde, slette eller markere som uden for scope), udarbejde en artikel 30-fortegnelse og masseslette forældet data.

**Hvad scanneren gennemgår:**
- Microsoft 365: Exchange e-mail, OneDrive, SharePoint, Teams
- Google Workspace: Gmail, Google Drev
- Lokale og netværksbaserede filmapper (herunder SMB/NAS-drev)

**Hvad den finder:**
- CPR-numre
- Telefonnumre, e-mailadresser, postadresser
- Bankkontonumre og IBAN-numre
- Navne og organisationsnavne
- Fotografier med genkendelige ansigter (valgfrit)
- GPS-placeringsdata indlejret i billedfiler

---

## 2. Overblik over brugerfladen

Når du åbner scanneren, er skærmen inddelt i tre områder:

```
┌─────────────────┬──────────────────────────────────────────┐
│                 │  Topbjælke: Scan-knap, profiler, handlinger│
│   Venstre panel ├──────────────────────────────────────────┤
│                 │                                           │
│  - Kilder       │         Resultater / scanningsforløb      │
│  - Indstillinger│                                           │
│  - Konti        │                                           │
│  - Statistik    ├──────────────────────────────────────────┤
│                 │               Aktivitetslog               │
└─────────────────┴──────────────────────────────────────────┘
```

**Venstre panel** — vælg hvad der skal scannes og hvordan.  
**Topbjælke** — start en scanning, vælg profiler, og tilgå eksporter og indstillinger.  
**Resultatområde** — fundne elementer vises her, mens scanningen kører.  
**Statuslinje** — vises lige over aktivitetsloggen og angiver hvilken kilde der scannes, hvem der scannes, og hvor langt scanningen er.  
**Aktivitetslog** — viser statusbeskeder i realtid under scanningen. Klik på **▾**-pilen i loggens overskrift for at folde panelet sammen eller ud. Du kan også filtrere loggen til kun at vise fejl, kopiere al logtekst til udklipsholderen og ændre størrelsen på panelet ved at trække i håndtaget øverst på panelet.

### Mørkt / lyst tema

Klik på **🌙**-knappen øverst til højre for at skifte mellem mørkt og lyst tema. Din præference huskes.

---

## 3. Forbindelse til dine datakilder

Inden du kan scanne, skal du forbinde mindst én datakilde. Klik på **Kilder** i topbjælken for at åbne kildestyringspanelet.

### 3.1 Microsoft 365

Fanen Microsoft 365 viser din aktuelle forbindelsesstatus. Hvis du ser en grøn prik og dit kontonavn eller lejernavn, er du allerede forbundet.

**Kilder du kan slå til og fra:**

| Skift | Hvad der scannes |
|-------|-----------------|
| Outlook | Exchange-postkasser (indbakke, sendt post, alle mapper) |
| OneDrive | Den enkelte brugers personlige cloud-lager |
| SharePoint | Team- og projektsider |
| Teams | Filer delt i Teams-kanaler |

Slå de kilder fra, du ikke ønsker at medtage. Disse indstillinger huskes.

### 3.2 Google Workspace

Fanen Google Workspace lader dig forbinde en Google Workspace-konto (tidligere G Suite) via en tjenestekonto, eller en personlig Google-konto via login.

**Kilder du kan slå til og fra:**

| Skift | Hvad der scannes |
|-------|-----------------|
| Gmail | Alle e-mails i den enkelte brugers indbakke og labels |
| Google Drev | Alle filer ejet af eller delt med den enkelte bruger |

### 3.3 Lokale og netværksbaserede filer

Fanen **Filkilder** viser de lokale mapper og netværksdrev, du har konfigureret.

**Sådan tilføjer du en ny filkilde:**
1. Indtast en **Betegnelse** — et navn du kan genkende (f.eks. "Skolens Fællesmappe").
2. Indtast **Stien**:
   - Lokal mappe: `~/Dokumenter` eller `/Volumes/Drev`
   - Netværksdrev: `//nas-server/delt` eller `\\server\delt`
3. Hvis det er et netværksdrev, udfyldes felterne **SMB-vært**, **Brugernavn** og **Adgangskode** automatisk. Adgangskoden gemmes sikkert i systemets nøglering.
4. Klik på **Tilføj**.

Du kan tilføje så mange filkilder, du har brug for. De vil fremgå som valgbare kilder i venstre panel, når du er klar til at scanne.

---

## 4. Kør en scanning

### 4.1 Vælg dine kilder

I venstre panel under **Kilder** sætter du hak ved de kilder, du vil medtage. Du kan kombinere M365, Google og filkilder i samme scanning.

### 4.2 Vælg konti

Under **Konti** vises alle brugere tilknyttet din M365- og/eller Google-lejer.

- Brug **søgefeltet** til at finde bestemte personer.
- Brug knapperne **Alle / Ansat / Elev** til at filtrere efter rolle.
- Brug **Alle**- og **Ingen**-knapperne til at vælge eller fravælge alle på én gang.
- Sæt hak ved eller fjern hak fra enkeltpersoner.

For filkilder er kontovalg ikke relevant — alle filer i de valgte stier scannes.

### 4.3 Konfigurer indstillinger

Under **Indstillinger** kan du justere scanningen:

**Datofilter (Scan e-mails/filer fra)**  
Scan kun elementer ændret efter en bestemt dato. Hurtige forudindstillinger — **1 år**, **2 år**, **5 år**, **10 år**, **Alle** — lader dig vælge et interval med ét klik. Du kan også vælge en specifik dato med datovælgeren.

> Tip: "2 år" er et godt udgangspunkt for den første scanning. Du kan altid udvide til "Alle" bagefter.

**Scan e-mailindhold** — gennemgår selve teksten i e-mails. Aktiveret som standard.

**Scan vedhæftede filer** — gennemgår filer vedhæftet e-mails. Aktiveret som standard.

**Maks. vedhæftet filstørrelse** — spring vedhæftede filer over, der er større end denne grænse (standard 20 MB). Øg grænsen, hvis du vil kontrollere større dokumenter.

**Maks. e-mails pr. bruger** — stop efter at have scannet dette antal e-mails per person (standard 2.000). Øg det, hvis du har brug for fuld dækning.

### 4.4 Start scanningen

Klik på den blå **Scan**-knap i topbjælken.

En statuslinje viser:
- En farvet **kildemærkat** — **Outlook**, **OneDrive**, **SharePoint**, **Teams**, **Gmail**, **GDrive** eller **Local** — efterfulgt af det fulde navn på den konto, der scannes i øjeblikket
- En løbende optælling af scannede og fundne elementer
- Estimeret resterende tid

Resultater vises i hovedområdet efterhånden som de findes — du behøver ikke vente på, at scanningen er færdig, før du begynder at gennemgå dem.

Klik på **Stop** for at afbryde. Et kontrolpunkt gemmes automatisk, så du kan fortsætte senere.

### 4.5 Genoptag en afbrudt scanning

Hvis en scanning blev afbrudt (via stop, nedbrud eller lukning af programmet), vises et gult banner øverst i resultatområdet:

> Forrige scanning blev afbrudt — X scannet, Y fundet  
> **▶ Genoptag** · Start forfra

Klik på **▶ Genoptag** for at fortsætte fra det sted, scanningen slap. Klik på **Start forfra** for at kassere kontrolpunktet og begynde en ny scanning.

---

## 5. Forstå resultaterne

Hvert fundet element vises som et kort. Her er forklaringen på mærker og labels:

### Kildemærker

| Mærke | Betydning |
|-------|-----------|
| Outlook | Fundet i en Exchange-postkasse |
| OneDrive | Fundet i en brugers OneDrive |
| SharePoint | Fundet på et SharePoint-site |
| Teams | Fundet i en Teams-kanal |
| Gmail | Fundet i en Gmail-postkasse |
| Google Drev | Fundet i Google Drev |
| Lokal / Netværk | Fundet på et filshare |

### Risikoniveau

| Niveau | Betydning |
|--------|-----------|
| HØJ | Flere CPR-numre, særlige kategorier af data, ældre end opbevaringspolitikken eller eksternt delt |
| MELLEM | Et enkelt CPR-nummer med noget deling eller kontekstuel risiko |
| LAV | Et enkelt CPR-nummer, ikke delt, nyligt oprettet |

### Øvrige mærker

| Mærke | Betydning |
|-------|-----------|
| Tal (f.eks. **3**) | Antal CPR-numre fundet i elementet |
| **Delt** | Elementet er delt med andre brugere |
| **Ekstern** | Elementet er delt med nogen uden for organisationen |
| **Art. 9** | Særlige kategorier af oplysninger fundet (helbred, religion, biometriske data mv.) |
| **N ansigter** | N genkendelige ansigter registreret i et foto |
| **GPS** | Filen indeholder GPS-placeringsdata i metadata |

### Kortvisning vs. listevisning

Standardvisningen er **kortvisning**. Klik på **Liste** i filterbjælken for at skifte til en kompakt tabelvisning med sorterbare kolonner. Klik på **Gitter** for at skifte tilbage.

### Filtrering af resultater

Brug filterbjælken over resultaterne til at indsnævre visningen:

- **Søgefelt** — søg på navn, emne eller filsti.
- **Kildetype** — vis kun én kildetype.
- **Disposition** — vis elementer efter gennemgangsstatus.
- **Deling** — filtrer på delt / ekstern / alle.
- **Risiko** — vis kun Art. 9, fotos, GPS eller høj-risiko-elementer.
- **Rolle** — vis kun **Ansatte** eller **Elever**. Påvirker også eksporten: klikker du på **Excel** eller **Art.30**, mens en rolle er valgt, indeholder rapporten kun den pågældende gruppe, og filnavnet får suffikset `_elever` eller `_ansatte`.

---

## 6. Gennemgang og mærkning af fund

Klik på et resultatkort for at åbne forhåndsvisningspanelet i højre side af skærmen.

Forhåndsvisningen viser:
- Elementets navn eller e-mailens emne
- Kontoen (ejer / afsender)
- Kilde og ændringsdate
- Alle fundne CPR-numre og deres kontekst
- Øvrige personoplysninger registreret (telefon, e-mailadresse, IBAN mv.)
- Deling og ekstern adgangsinformation

### Angiv en disposition

Hvert element har en **Disposition**-rullemenu i forhåndsvisningspanelet. Vælg én af følgende:

| Disposition | Brug den når… |
|-------------|---------------|
| Ikke gennemgået | Endnu ikke vurderet — standardværdi |
| Opbevar — lovkrav | Du er lovpligtig til at beholde den |
| Opbevar — legitim interesse | Du har en legitim interesse i at beholde den |
| Opbevar — kontrakt | Nødvendig i forbindelse med en kontrakt |
| Slet — planlagt | Markeret til fremtidig sletning |
| Privat brug — uden for scope | Personligt element, ikke inden for GDPR-scopet |
| Slettet | Allerede slettet (angives automatisk ved sletning) |

Klik på **Gem** efter valget. En lille **✓ Gemt**-bekræftelse vises.

### Find alle elementer for en bestemt person

Klik på **🔍** i venstre panel (under Statistik) for at åbne **Registreret person**-opslaget. Indtast et CPR-nummer, og scanneren finder alle fundne elementer, der indeholder dette nummer. Du kan derefter slette dem alle i ét trin — i overensstemmelse med retten til sletning (GDPR artikel 17).

CPR-nummeret hashes inden søgningen og gemmes aldrig i klartekst.

---

## 7. Sletning af elementer

### 7.1 Sletning af et enkelt element

Med et element åbent i forhåndsvisningspanelet kan du angive dispositionen **Slet — planlagt** og bruge handlingsknappen til at slette det. E-mailen flyttes til mappen Slettet post; filer flyttes til papirkurven i den pågældende tjeneste.

### 7.2 Massesletning

Klik på **Slet**-knappen i filterbjælken for at åbne massesletningsvinduet.

1. **Indstil filtre** for at målrette de elementer, du ønsker at slette:
   - **Kildetype** — slet fra én kilde eller alle.
   - **Min. CPR-fund** — slet kun elementer med mindst dette antal CPR-numre.
   - **Ældre end dato** — slet kun elementer ændret inden en bestemt dato.
   - Klik på **🗓 Filter forældet** for automatisk at udfylde datoen ud fra din opbevaringspolitik.

2. Vinduet viser, hvor mange elementer der matcher dine filtre.

3. Klik på den røde **Slet matchende elementer**-knap for at fortsætte.

4. En statuslinje viser sletningerne i realtid. E-mails flyttes til **Slettet post**; filer flyttes til **papirkurven**.

En fuldstændig revisionslog over alle sletninger (hvad der er slettet, hvornår og hvorfor) medtages i artikel 30-rapporten.

---

## 8. Profiler — gem dine scanningsindstillinger

En profil gemmer dine valgte kilder, konti, scanningsindstillinger og datoindstillinger, så du kan genbruge dem uden at konfigurere alt på ny hver gang.

### Gem en profil

Konfigurer venstre panel præcis som du ønsker det — herunder hvilke M365-kilder, Google-kilder og lokale filkilder der er aktiveret, hvilke konti der er valgt, og alle indstillinger — og klik derefter på **Gem**-knappen i topbjælken. Indtast et navn og klik OK. Profilen gemmes og vælges med det samme.

### Anvend en profil

Klik på profil-rullemenuen i topbjælken og vælg en profil. Alle indstillinger i venstre panel — kilder, konti, indstillinger og datofilter — indlæses på én gang. Venstre panel viser derefter din aktive tilstand, og du kan justere hvad som helst, inden du scanner.

En **Ryd**-knap vises ved siden af rullemenuen, når en profil er valgt. Klik på den for at rydde profil­etiketten uden at ændre indstillingerne i venstre panel. Det er nyttigt, når du vil køre en engangsscan uden at overskrive en gemt profil.

### Administrer profiler

Klik på **Profiler** for at åbne profil­administrations­panelet. Her kan du:

- **Redigere** en profil — ændre navn, beskrivelse, kilder, konti eller indstillinger.
- **Duplikere** en profil — nyttigt som udgangspunkt for en variant.
- **Slette** en profil.

> Bemærk: Redigering af en profil påvirker ikke scanninger, der allerede er gennemført med den pågældende profil.

---

## 9. Rapporter og eksport

### 9.1 Excel-eksport

Klik på **Excel** i filterbjælken for at downloade de aktuelle resultater som en Excel-projektmappe. Projektmappen indeholder:
- Et oversigtsfaneblad med scanningsdato, antal elementer og kildefordeling.
- Et separat faneblad for hver kildetype (Outlook, OneDrive, SharePoint, Teams, Gmail, Google Drive, Lokal, Netværk).
- Alle fundne elementer, herunder kilde, konto, CPR-antal, risikoniveau, delingsstatus og disposition.

Knapperne **Excel** og **Art.30** er altid tilgængelige — også efter genstart af programmet — og eksporterer resultaterne fra den seneste afsluttede scanningssession uden at kræve en ny scanning.

Excel-filen er det primære arbejdsdokument til din interne gennemgangsproces.

### 9.2 GDPR Artikel 30-rapport (Word-dokument)

Klik på **Art.30** i filterbjælken for at generere et Word-dokument, der opfylder kravet i GDPR artikel 30 om at føre en fortegnelse over behandlingsaktiviteter.

Dokumentet indeholder:
- **Resumé** — scanningsdato, samlet antal elementer, CPR-fund pr. kilde.
- **Datakategorier** — hvilke typer personoplysninger der er fundet.
- **Datafortegnelse** — den fulde liste over fundne elementer.
- **Opbevaringsanalyse** — elementer ældre end din opbevaringspolitik, fordelt på kilder.
- **Særlige kategorier (Art. 9)** — helbreds-, biometriske og andre følsomme oplysninger.
- **Fotografier / biometriske data** — hvis ansigtsgenkendelse var aktiveret.
- **GPS-data** — filer med indlejrede placeringsoplysninger.
- **Compliance-tendens** — antal fundne elementer på tværs af dine seneste 20 scanninger.
- **Revisionslog for sletninger** — en komplet dokumentation af alle sletninger foretaget via scanneren.
- **Metode** — hvordan scanningen er udført og det juridiske grundlag.
- **Noter om elevdata** — vejledning om krav til forældresamtykke for børn under 15 år.

---

## 10. Del resultater med en gennemganger

Du kan give en DPO, skoleleder eller compliance-koordinator skrivebeskyttet adgang til resultatgitteret — herunder mulighed for at mærke dispositioner — uden at give dem adgang til scanningskontroller, loginoplysninger eller indstillinger.

### 10.1 Token-links

Klik på **🔗**-knappen øverst til højre i topbjælken for at åbne delingspanelet.

1. Angiv eventuelt en **Betegnelse** for at identificere, hvem linket er til (f.eks. "DPO-gennemgang april 2026").
2. Vælg et **Rolleomfang** — **Alle roller**, **Ansatte** eller **Elever**. Et afgrænset link begrænser modtageren til elementer tilhørende den valgte rollegruppe; de kan ikke se andre elementer, og rollefilteret er låst i deres visning.
3. Vælg en **Udløbsdato** — 7 dage, 30 dage, 90 dage, 1 år eller Aldrig.
4. Klik på **Opret**. Der genereres et unikt link: `http://host:5100/view?token=…`
5. Klik på **Kopiér** for at kopiere linket til udklipsholderen, og send det til gennemgangeren.

Gennemgangeren åbner linket i en browser. De kan se resultatgitteret (afgrænset til det tilladte rolleomfang) og mærke dispositioner, men kan ikke starte scanninger, ændre indstillinger, se loginoplysninger eller slette elementer.

**Administrer eksisterende links**

Delingspanelet viser alle aktive links. Hver række viser betegnelse, rollemærkat (hvis afgrænset), udløbsdato og hvornår linket sidst blev brugt. Klik på **Kopiér** for at kopiere et link igen, eller **Tilbagekald** for at gøre det ugyldigt med det samme.

> **Tip:** I skoler og kommuner er det almindeligt at have separate DPO'er eller compliance-ansvarlige for henholdsvis ansatte og elever. Opret ét afgrænset link til hver — eleve-DPO'en vil kun se elevdata, og ansatte-DPO'en vil kun se ansattedata.

### 10.2 Viewer-PIN

Som alternativ til token-links kan du angive en numerisk PIN-kode (4–8 cifre) under **Indstillinger → Sikkerhed → Viewer-PIN**. Alle, der kender PIN-koden, kan åbne `http://host:5100/view` i en browser, indtaste PIN-koden og få adgang til den skrivebeskyttede visning i hele browserens session.

For at angive eller ændre PIN-koden skal du indtaste den nye kode i feltet **Ny PIN** og klikke på **Gem PIN**. Klik på **Ryd PIN** for at fjerne den.

> **Sikkerhedsnote:** Token-links er mere sikre end en PIN-kode, fordi hvert link kan tilbagekaldes individuelt, har en udløbsdato og kan afgrænses til en bestemt rollegruppe. Brug PIN-indstillingen kun til betroede interne gennemgangere på dit lokale netværk, der har brug for adgang til alle resultater.

### 10.3 Hvad gennemgangeren kan gøre

| Handling | Tilladt |
|----------|---------|
| Gennemse resultatgitter | Ja |
| Filtrere og søge i resultater | Ja |
| Åbne forhåndsvisning | Ja |
| Mærke dispositioner | Ja |
| Eksportere til Excel | Ja |
| Eksportere Artikel 30-rapport | Ja |
| Starte eller stoppe en scanning | Nej |
| Se eller ændre loginoplysninger | Nej |
| Slette elementer | Nej |
| Tilgå indstillinger | Nej |
| Oprette eller tilbagekalde viewer-links | Nej |
| Se elementer uden for deres rolleomfang | Nej |

---

## 11. Planlagte scanninger

Gå til **Indstillinger → Planlægger** for at konfigurere automatiske scanninger.

### Opret en planlagt scanning

1. Klik på **+ Tilføj planlagt scanning**.
2. Giv jobbet et navn.
3. Vælg frekvens: **Dagligt**, **Ugentligt** eller **Månedligt**.
4. For ugentlige scanninger vælges ugedag. For månedlige vælges dag i måneden.
5. Angiv det tidspunkt, scanningen skal køre.
6. Vælg en **Profil** — scanneren bruger den pågældende profils kilder, konti og indstillinger.
7. Aktiver eventuelt:
   - **Send rapport automatisk** — send Excel-rapporten pr. e-mail til dine konfigurerede modtagere efter hver scanning.
   - **Håndhæv opbevaringspolitik** — slet automatisk elementer ældre end din opbevaringspolitik efter hver scanning.
8. Klik på **Gem**.

Planlæggerikatoren i topbjælken viser dato og tidspunkt for den næste planlagte scanning ("Næste: …").

### Se seneste kørsler

Fanen Planlægger viser historik over seneste kørsler med starttidspunkt, status og antal fundne elementer.

---

## 12. E-mailrapporter

Gå til **Indstillinger → E-mailrapport** for at konfigurere e-mail-afsendelse.

### Opsætning af SMTP

Udfyld oplysningerne for din udgående mailserver:

| Felt | Eksempel |
|------|----------|
| SMTP-vært | smtp.office365.com |
| Port | 587 |
| Brugernavn | scanner@skole.dk |
| Adgangskode | (din e-mailadgangskode eller app-adgangskode) |
| Afsenderadresse | scanner@skole.dk |
| Modtagere | dpo@skole.dk; it@skole.dk |

Klik på **Gem** for at gemme, og klik derefter på **Test** for at sende en test-e-mail og bekræfte, at konfigurationen virker.

> Hvis din konto har MFA (to-faktor-godkendelse) aktiveret, kan du ikke bruge din almindelige adgangskode. Du skal oprette en **app-adgangskode** i din kontos sikkerhedsindstillinger:
> - **Personlig Microsoft-konto**: account.microsoft.com/security → App-adgangskoder
> - **Gmail**: myaccount.google.com → Sikkerhed → 2-trinsbekræftelse → App-adgangskoder

### Send en rapport manuelt

Klik på **Send nu** for øjeblikkeligt at sende den aktuelle Excel-rapport pr. e-mail til alle konfigurerede modtagere.

---

## 13. Sikkerhedskopi og gendannelse af database

Alle scanningsresultater, dispositioner og sletningsrevisionsloggen gemmes i en lokal database. Det anbefales at tage regelmæssige sikkerhedskopier.

Gå til **Indstillinger → Database**.

### Sikkerhedskopi (Eksport)

Klik på **Eksporter** for at oprette en `.zip`-sikkerhedskopi af din database. Gem den på et sikkert sted.

### Gendannelse (Import)

Klik på **Importer** for at gendanne fra en sikkerhedskopi. To tilstande er tilgængelige:

| Tilstand | Hvornår du bruger den |
|----------|-----------------------|
| Flet (sikker) | Tilføj dispositioner og sletningslog fra sikkerhedskopien til dine eksisterende data. Brug denne til at samle data fra flere installationer. |
| Erstat (fuld gendannelse) | Slet alt eksisterende og gendan sikkerhedskopien fuldstændigt. Brug denne til at flytte til en ny maskine eller gendanne efter datatab. Kræver bekræftelse med admin-PIN. |

### Nulstil database

Klik på **Nulstil database** for at slette alle scanningsdata, dispositioner og sletningslog. Dette kan ikke fortrydes. Hvis en admin-PIN er sat, skal du indtaste den for at fortsætte.

---

## 14. Indstillinger — oversigt

### Fanen Generelt

| Indstilling | Beskrivelse |
|-------------|-------------|
| Tema | Mørkt eller lyst |

### Fanen Sikkerhed

| Indstilling | Beskrivelse |
|-------------|-------------|
| Admin-PIN | Valgfri PIN-kode, der beskytter destruktive handlinger (nulstil database, erstat ved import) |
| Viewer-PIN | Valgfri 4–8-cifret PIN-kode, der giver alle adgang til `/view` i en browser som skrivebeskyttet gennemganger uden et token-link |

### Avancerede scanningsindstillinger

Disse indstillinger findes i venstre panel under **Indstillinger**:

**Delta-scanning** — efter din første fulde scanning kan du aktivere dette for kun at scanne elementer, der er ændret siden sidste scanning. Meget hurtigere til løbende kontrol. Knappen "Ryd tokens" tvinger den næste scanning til at være en fuld scanning.

**Søg efter ansigter i billeder** — langsommere scanning, der registrerer fotografier med genkendelige menneskelige ansigter. Markerer dem som artikel 9 biometriske data. Anbefales til skoler, der opbevarer elevfotos.

**Ignorer GPS i billeder** — når aktiveret, flagges billeder ikke, hvis GPS-koordinater i billedets metadata er det eneste PII-signal. Nyttigt ved scanning af elevkonti: smartphones indlejrer automatisk GPS-koordinater i alle kamerabilleder, hvilket ellers ville generere mange lavprioriterede fund i en skolekontekst. Hvis et billede allerede er flagget af en anden årsag (ansigter, EXIF-forfatterfelter), vises GPS-koordinaterne stadig i detaljekortet.

**Min. CPR-antal pr. fil** — en fil flagges kun, hvis den indeholder mindst dette antal *distinkte* CPR-numre. Standardværdien er 1 (nuværende adfærd). Sæt til 2 for at undgå falske positive ved elevscanninger: en elevs samtykkeerklæring eller indmeldelsesformular indeholder typisk kun elevens eget CPR-nummer, mens en klasselist eller karakteroversigt med flere elevers CPR-numre stadig vil blive rapporteret.

**Opbevaringspolitik** — når aktiveret, markeres elementer ældre end det angivne antal år som forældet. Regnskabsårets afslutning bestemmer, hvordan skæringsdatoen beregnes:

| Indstilling | Beregning af skæringsdato |
|-------------|--------------------------|
| Løbende (fra i dag) | I dag minus N år |
| 31 dec (Bogføringsloven) | Seneste 31. december minus N år |
| 30 jun / 31 mar | Seneste forekomst af den dato minus N år |

---

## 15. Ofte stillede spørgsmål

**Gemmer scanneren CPR-numre?**  
Nej. CPR-numre fundet under en scanning gemmes kun som et antal (f.eks. "3 CPR-numre fundet") og som en SHA-256-hash, der bruges til personopslag. Det faktiske nummer skrives aldrig til databasen.

**Hvad sker der, når jeg sletter elementer via scanneren?**  
E-mails flyttes til brugerens **Slettet post**-mappe i Exchange — de slettes ikke permanent og kan gendannes af brugeren eller en administrator. Filer flyttes til **papirkurven** i den pågældende tjeneste (OneDrive, SharePoint, filsystem). Permanent sletning kræver en efterfølgende handling af brugeren eller administrator.

**Kan jeg scanne uden at forbinde til Microsoft 365?**  
Ja. Du kan scanne lokale og SMB-filshares uden nogen M365- eller Google-forbindelse. Åbn **Kilder**, gå til fanen **Filkilder**, og tilføj dine filstier.

**Hvad er delta-scanning, og hvornår skal jeg bruge det?**  
Delta-scanning bruger Microsoft Graphs ændringstokens til kun at hente elementer ændret siden den seneste scanning. Det er ideelt til regelmæssige (f.eks. ugentlige) compliance-tjek efter, at du har gennemført en fuld basisscan. Aktiver det i afsnittet Indstillinger i venstre panel.

**Scanningen stoppede — kan jeg fortsætte, hvor den slap?**  
Ja. Når du starter scanningen igen, vil et gult banner tilbyde at genoptage fra kontrolpunktet. Klik på **▶ Genoptag** for at fortsætte. Hvis du foretrækker at starte forfra, klikker du på **Start forfra**.

**Hvordan dokumenterer jeg compliance, hvis vi bliver auditeret?**  
Brug **Art.30**-knappen til at eksportere artikel 30-rapporten. Det er et Word-dokument, der dækker din datafortegnelse, opbevaringsanalyse, sletningslog og metode — præcis hvad en tilsynsmyndighed (Datatilsynet) typisk anmoder om.

**Hvad gør filteret "Elev / Ansat"?**  
Scanneren klassificerer brugere som ansatte eller elever ud fra deres Microsoft 365-licenstype eller Google Workspace-organisationsenhed. Du kan bruge dette filter i kontolisten til at begrænse en scanning til kun ansatte, kun elever eller en bestemt person. Det er nyttigt, fordi reglerne for behandling af elevdata — særligt for børn under 15 år — adskiller sig fra reglerne for medarbejderdata i henhold til databeskyttelsesloven.

**Hvordan tilføjer jeg en konto, der ikke er på listen?**  
I kontoafsnittet i venstre panel er der et felt **+ Tilføj konto manuelt**. Indtast e-mailadressen eller UPN'en, og den tilføjes til den aktuelle sessions kontoliste.

**Kører scanneren? Jeg kan ikke se en statuslinje.**  
Tjek aktivitetsloggen nederst på skærmen. Hvis en scanning kører, vises der beskeder her. Hvis du ikke ser noget, er scanningen muligvis afsluttet eller ikke startet. Kontrollér også, at du har valgt mindst én kilde og mindst én konto.

**Kan en gennemganger mærke dispositioner uden adgang til scanningskontrollerne?**  
Ja. Brug **🔗 Del**-knappen til at oprette et skrivebeskyttet viewer-link eller angiv en Viewer-PIN under Indstillinger → Sikkerhed. Gennemgangeren åbner linket i sin browser og kan gennemse resultater og mærke dispositioner uden at se loginoplysninger, kilder eller scanningsknapper. Se afsnit 10 for detaljer.

---

*GDPR Scanner v1.6.14 — teknisk opsætning og konfiguration: se README.md*
