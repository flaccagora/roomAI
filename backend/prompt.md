Analizza attentamente il seguente annuncio di affitto e verifica se rispetta **TUTTI** i criteri riportati di seguito.  

### Criteri di valutazione:
1. Deve essere un annuncio che **offre** una casa/stanza in affitto, oppure una ricerca di **coinquilino**. Escludi tutti gli annunci in cui si è alla ricerca di un posto, assicurati che stiano offrendo qualcosa. 
2. Deve trattarsi di una **camera singola** (non doppia né condivisa) **oppure di un intero appartamento**.  
3. Il prezzo deve essere **inferiore a 600 € al mese** (considera solo l’affitto mensile, escluse spese straordinarie).  
   - Se il prezzo non è specificato, consideralo come **inferiore a 650 €**.  
4. L’offerta non deve essere esclusivamente rivolta a ragazze o solo coinquiline donne ma anche a uomini vanno bene studenti, lavoratori o altro.  

### Procedura anti-errore per il punto 1 (OBBLIGATORIA)
Prima di valutare gli altri criteri, CLASSIFICA l’annuncio in uno dei seguenti tipi (non restituire questa classificazione nel JSON, usala solo per decidere):
- OFFERTA_ALLOGGIO: chi scrive sta offrendo una stanza/casa o cerca un coinquilino/subentrante.
- RICERCA_ALLOGGIO: chi scrive sta cercando una stanza/casa per sé (o per sé + altri).
- ALTRO: post informativo, segnalazione, inoltro vago, richiesta di info, ecc.

Regola decisionale per il punto 1:
- ACCETTA il punto 1 solo se il tipo è OFFERTA_ALLOGGIO.
- SCARTA se il tipo è RICERCA_ALLOGGIO o ALTRO.

### Istruzioni per la risposta:  
- Rispondi sinteticamente in formato JSON con:  
{"status": "ACCETTATO" o "SCARTATO", "motivo": "Analisi dei criteri rispettati 1:\n<reason>\n2:\n<reason>\n3:\n<reason>\n4:\n<reason>"}

### Annuncio da valutare:


