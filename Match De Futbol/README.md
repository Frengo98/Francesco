# Tabellino

App locale per registrare i risultati settimanali e le statistiche individuali. Chi visita l'app può consultare dati e storico; solo chi conosce la password amministratore può inserire giocatori e partite.

## Avvio su Windows

1. Apri il Prompt dei comandi nella cartella `app`.
2. Avvia il server:

   ```cmd
   python server.py
   ```

   Il server ti chiederà la password amministratore all'avvio. In alternativa, puoi impostare `FOOTBALL_ADMIN_PASSWORD` prima di avviarlo. Non inserire la password direttamente nel comando se la cronologia della console è condivisa.
3. Apri <http://localhost:8765> nel browser. Lascia aperta la finestra del Prompt dei comandi mentre usi l'app.

I dati vengono salvati in `app\data\partite.json` e aggiornati a ogni modifica nel file Excel `app\data\statistiche_partite.xlsx` (fogli **Statistiche**, **Partite** e **Dettaglio**). Non aprire il file Excel mentre registri dati, per evitare che Excel ne impedisca l'aggiornamento.

## Accesso da Internet tramite link (temporaneo)

Puoi condividere l'app senza acquistare un dominio usando un [Cloudflare Quick Tunnel](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/). Installa `cloudflared`, poi apri due finestre del Prompt dei comandi nella cartella 

1. Nella prima finestra avvia l'app sul computer locale:

   ```cmd
   python server.py
   ```

2. Nella seconda avvia il tunnel:

   ```cmd
   cloudflared tunnel --url http://localhost:8765
   ```

   `cloudflared` mostrerà un URL `https://....trycloudflare.com`. Chiunque abbia il link potrà visualizzare dati, classifiche e partite senza inserire email o password. Il link può essere inoltrato; la password amministratore dell'app protegge solo le operazioni di modifica.

Non usare `--listen-url http://+:8765/` con questo metodo: il server deve restare accessibile solo dal computer che ospita l'app. Non aprire o inoltrare la porta 8765 sul router. Il computer, il server Python e `cloudflared` devono restare accesi. L'URL cambia quando si riavvia il tunnel; questa modalità è per prove e uso temporaneo, non offre garanzia di disponibilità e Cloudflare instrada il traffico del sito.

## Inserimento dei totali pregressi

Per caricare i dati aggregati delle partite già giocate, accedi come amministratore e usa il riquadro **Totali delle partite pregresse**. Inserisci il numero complessivo di partite e, per ogni giocatore, i totali di presenze, gol, assist, autogol, MVP, vittorie, sconfitte e pareggi. I valori vengono sommati alle partite dettagliate che registrerai in seguito; non vengono creati risultati o schede fittizie per le partite pregresse.

Nel riepilogo generale il numero di partite include sia quelle pregresse sia quelle registrate con il dettaglio. Lo storico e il foglio **Dettaglio** mostrano invece soltanto le partite inserite singolarmente. Per i dati già presenti prima di questa funzione, il conteggio iniziale delle partite pregresse è 8 ed è modificabile dal riquadro.

Per ogni giocatore, le presenze pregresse devono essere uguali alla somma di vittorie, sconfitte e pareggi; il salvataggio segnala i valori incoerenti. Il punteggio totale assegna 3 punti per vittoria, 2 per MVP e 1 per pareggio. La classifica mostra la posizione calcolata in base al punteggio totale; a pari punti i giocatori condividono la posizione. Le intestazioni della classifica sono selezionabili per ordinare ciascuna colonna in ordine crescente o decrescente. La mini classifica mostra le statistiche della partita dettagliata con la data più recente e si aggiorna quando registri nuove partite.

Nella sezione **Ultime partite**, ogni gara mostra la composizione di entrambe le squadre e, per ciascun giocatore presente, gol, assist, autogol ed eventuale MVP.

In modalità amministratore puoi modificare una partita già registrata con il pulsante **Modifica partita** nella scheda della gara: data, risultato, squadre e statistiche aggiornano anche la classifica e il file Excel. Nel modulo di registrazione i giocatori sono elencati in ordine alfabetico per nome e cognome.

## Accesso solo in rete locale (facoltativo)

Questa modalità rende l'app accessibile solo ai dispositivi collegati alla stessa rete Wi-Fi/LAN; non usarla per condividerla via Internet. Avvia il server in ascolto su tutte le interfacce:

```cmd
py server.py --listen-url http://+:8765/
```

Gli altri dispositivi possono aprire `http://INDIRIZZO-IP-DEL-PC:8765`; se Windows Firewall lo richiede, autorizza Python all'accesso sulla rete privata. La password amministratore non viene memorizzata nei file dell'app. Mantieni la password riservata: la connessione locale usa HTTP e non è cifrata.