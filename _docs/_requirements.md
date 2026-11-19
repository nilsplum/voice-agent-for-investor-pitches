# Anforderungen

**AI Voice-Agent**

## Aufgabe

Ein web-basierter Voice-Agent, der ein Erstgespräch mit einem Startup führt. Der Nutzer spricht über das Mikrofon im Browser, der Agent versteht das Gesprochene, generiert per KI eine Antwort und spricht sie zurück.

Der Rahmen: Ein Gründer stellt sein Startup vor, der Agent führt durch das Gespräch und fragt nach, bis er ein belastbares Bild hat. Also Team, Produkt und Stand der Entwicklung, Traktion, Markt und Wettbewerb, Finanzierungsbedarf und geplante Runde. Am Ende fasst der Agent zusammen und legt das Ergebnis strukturiert ab.

## Anforderungen

### Voice-Erfahrung im Browser

- Geringe Latenz: Antworten kommen schnell, idealerweise unter 1 bis 2 Sekunden vom Ende der Eingabe bis zum Beginn der Audioantwort.
- Natürliche Sprachausgabe: TTS soll sich möglichst wenig nach Maschine anhören.
- Start/Stopp-Steuerung: Gespräch per Button starten und beenden.

### Gesprächsführung

- Der Agent fragt nach, statt nur zu antworten. Wenn eine Angabe fehlt oder vage bleibt, hakt er einmal nach.
- Roter Faden: Der Agent behält im Gespräch, was schon geklärt ist, und wiederholt sich nicht.

### Transkript & Gesprächs-Historie

- Gesprächsverlauf sichtbar (wer hat was gesagt).
- Vergangene Gespräche mit Zeitstempel einsehbar.

### Konfigurierbarkeit

- Mind. 2 Einstellungen anpassbar (z. B. Name des Agents, Tonalität, Sprache, System-Prompt, Fragenkatalog).

### Bonus

- Tool Calling: zum Beispiel das Gesprächsergebnis strukturiert speichern (Startup, Sektor, Stage, Team, Traktion, Finanzierungsbedarf, nächster Schritt) oder eine Websuche zum genannten Startup.
- Streaming-Antworten.
- Gutes UI/UX.

## Hilfreiche Tools

Nur als Orientierung, kein Muss.

| Kategorie | Tools |
|---|---|
| Echtzeit-Voice | LiveKit, VAPI |
| Speech-to-Text | Deepgram, AssemblyAI |
| Text-to-Speech | ElevenLabs, OpenAI TTS, Google Cloud TTS |
| LLM | GPT-5.x, Claude Opus/Sonnet, Gemini |
