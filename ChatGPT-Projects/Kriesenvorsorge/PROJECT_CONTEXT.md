# Kriesenvorsorge

## Zweck

Praktische Vorsorge, Warnung und robuste Reaktion auf Unwetter, Stromausfälle und andere Krisenlagen.

## Bekannte Themen

- Regionale Unwetterwarnungen
- „MOEP“-Alarm und Alarmabläufe
- Neuer MultiPlus im Einsatz
- Technische und menschliche Vorbereitung
- Rückblick auf konkrete Ereignisse und daraus abgeleitete Verbesserungen

## Leitlinien

- Sicherheitsrelevante Meldungen sachlich prüfen und nicht verharmlosen.
- Technik, Wasser, Vorräte, Wissen, Kommunikation und Nachbarschaft gemeinsam betrachten.
- Alarmketten müssen verständlich, redundant und praktisch erprobt sein.

## Bestehende Home-Assistant-Logik

- Prüft alle fünf Minuten die aktuelle Warnstufe und Vorwarnstufe für den Kreis Germersheim.
- Berücksichtigt Gewitter, Sturm und Starkregen ab Warnstufe 3; Vorwarnungen dürfen innerhalb der nächsten 30 Minuten beginnen.
- Verhindert Wiederholungen innerhalb einer Stunde.
- Warnstufe 3 aktiviert eine Vorwarnung/„DEFCON 2“, Warnstufe 4 eine deutlichere „DEFCON 1“-Alarmierung.
- Meldungen laufen über Mobilbenachrichtigung und mehrere Alexa-Geräte. Flur-/Notbeleuchtung wird parallel eingeschaltet und schrittweise heller geregelt; nachts ist das Verhalten zurückhaltender.

## Beobachtungen und Folgerungen

- Netzspannungsverläufe werden am Hausanschlusspunkt gemessen und auf Lücken, Ausfälle und hohe PV-bedingte Spannung geprüft.
- Bei zusätzlicher voller PV-Einspeisung wurde ein Risiko in Richtung etwa 254 V diskutiert. Die eigene Inselversorgung gilt als vorbereitet; die Analyse soll deshalb auch Wasser, Versorgung, Hitze, Netzausfälle und regionale/internationale Abhängigkeiten einbeziehen.
- Der Baumeister Hobbit plant anhand beobachteter Schäden ebenfalls Schutzmaßnahmen; Nachbarschaftsvorsorge soll gemeinsam gedacht werden.
