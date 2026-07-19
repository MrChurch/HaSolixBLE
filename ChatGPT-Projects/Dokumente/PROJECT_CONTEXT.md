# Dokumente

## Zweck

Technische Anlagen- und Notfalldokumentation für Inselbetrieb, Brandschutz, Victron MultiPlus und Sunny Boy.

## Unterhaltungen

- Brandschutz-Anlagendokumentation
- Dokumentation MultiPlus Master
- Notfall-PDF Victron-Inselbetrieb
- Notfallsetup AC-Coupling

## Erkannte Dateien

- `Smart_Lumi_Notfallhandbuch_Victron_Inselbetrieb_Top20_Fehler.pdf`
- `Smart_Lumi_Notfallhandbuch_Sunny_Boy_AC_Out.pdf`

## Qualitätsziel

Dokumente sollen im Störungsfall schnell nutzbar, eindeutig, versionsbezogen und ohne Cloud-Abhängigkeit verfügbar sein. Schaltzustände, Prüfungen, Risiken und sichere Rückfallwege klar dokumentieren.

## Bekannte Anlagenstruktur

- Drei Victron MultiPlus 48/3000/35-32 im Parallelverbund auf einer Phase; der hintere GX-Multi ist Master, danach Slave 1 und Slave 2. Die im Sprachchat genannte Master-Seriennummer beginnt mit `c8`; vor Verwendung gegen das Typenschild prüfen.
- DC-Bus mit Cerbo/GX-Steuerung, MPPT 150/35 und MPPT 150/45.
- Mehrere Pytes-Batterieabgänge sowie drei 35-mm²-Abgänge zu den Multis; genaue Pytes-Typbezeichnungen aus der Spracherkennung vor einer finalen Dokumentation am Gerät verifizieren.
- DC-seitiger Überspannungs-/Blitzschutz vor den PV-Modulen, gemeinsame Erdung am Tiefenerder.
- AC-seitig ABB-Verteilung, Schneider-C32-Leistungsschutz, Victron-Smart-Meter und zwei Überspannungsschutzgeräte.

## Brandschutzstand

- Notbeleuchtung und Notlicht vorhanden.
- Zwei 6-l-Schaumlöscher nach ISO 7010; einer davon für zwei Jahre geprüft.
- Ein 750-ml-Löscher für Elektrobrände bei Schaltschrank und Batterien.
- ABB Mistral65-Verteiler.
- 35-mm²-Batterie-/Multi-Leitungen, Hauptzuleitungen und PV-Zuleitungen optisch beziehungsweise thermisch geprüft; der überwiegende Teil der Leitungen liegt in brandfestem Kabelkanal.
