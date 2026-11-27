A MyIssueDeck egy helyi hibakövető emberek és MI-alapú programozó ügynökök számára. Ez az oldal az irányítópultot mutatja be. A tartalomjegyzékből egy témára ugorhat; a böngésző keresője (Ctrl+F) ezen az oldalon szavakat keres.

## Első lépések {#start}

- **Jelentkezzen be** hozzáférési tokennel a bejelentkezési oldalon. A tokeneket a Beállítások oldalon hozhatja létre (lásd: [Beállítások](#settings)).
- A **bal oldali panel** az aktuális projekt nézeteit (Áttekintés, Kanban, Lista, Keresés), az *Új elem* gombot, a Beállításokat, a projektek listáját és legalul ezt a Súgót tartalmazza.
- A **felső sávban** van a keresőmező (nyomja meg a `/` billentyűt), az élő frissítések kapcsolatjelzője, a **nyelvlista** és a Beállítások hivatkozás.
- Az alapértelmezett nyelvet és a világos vagy sötét témát a Beállítások oldalon adhatja meg; a nyelvet bárki bármikor átállíthatja a nyelvlistával.

## Projektek {#projects}

- A projekt önálló nyilvántartás saját fajtákkal, állapotokkal, ágakkal és kiegészítő mezőkkel. Projektet a bal oldali panel alján lévő *Projektek* listában válthat.
- Az **Új projekt** sablonból hoz létre projektet (alap, ügynök-munkafolyamat, szoftvercsapat). Projekt pillanatképből is létrehozható (lásd: [Importálás és exportálás](#import-export)).
- Az Áttekintésen a **Pillanatkép exportálása** az egész projektet ZIP-fájlként tölti le. A **Projekt törlése** a projekt kulcsának begépelését kéri; előbb biztonsági pillanatkép készül, és a törlést megtagadja, amíg ügynöki munkamenet aktív.

## Elemek, fajták és állapotok {#items}

- Az elemnek azonosítója (például `FEAT-0001`), fajtája (funkció, hiba, feladat, probléma ... a projekt szerint), állapota, címe, **Markdown** formátumú tartalma, címkéi, kiegészítő mezői, hivatkozásai, kapcsolatai és tevékenységi naplója van.
- Elemet az *Új elem* gombbal (billentyű: `n`) hozhat létre. Az űrlap előnézetet mutat a Markdownról. Az elemet megnyitva szerkesztheti, megjegyzést fűzhet hozzá, és láthatja a munkameneteit.
- Az **állapotok** az ötlettől a kész elemig viszik az elemet (például Javasolt, Folyamatban, Blokkolva, Kiadásra kész, Kész). A kiadást igénylő állapotot, általában a *Kész*-et az elem **kiadásával** éri el: rögzítik az ágat és a verziót (például egy commitot). Az ügynökök ezt az API-n vagy az MCP-n (`ship_item`) keresztül teszik.
- **Idő:** a *Becsült idő* és az *Eltöltött idő* órában van megadva, és az Áttekintésen összegződik.
- A **kapcsolatok** elemeket kötnek össze: *blokkolja* / *blokkolja őt*, és *kapcsolódik*.
- A törölt elem csak el van rejtve, és visszaállítható.

## Kanban tábla {#board}

- Minden oszlop egy állapot. **Húzzon egy kártyát** másik oszlopba az állapot módosításához. Üzenet erősíti meg a módosítást; ha elutasítják, a kártya visszakerül.
- A tábla újratöltés nélkül követi mások és az MI-ügynökök módosításait. A húzás alatt álló kártyát soha nem cseréli le.
- A tábla fölötti, választható *Aktív ügynöki munkamenetek* kisalkalmazást a Beállításokban kapcsolhatja be.

## Lista, keresés és szűrők {#list-search}

- A **Lista** táblázatban mutatja az elemeket. A szűrőkhöz nyomja meg az `f` billentyűt (állapot, fajta, címke, kiegészítő mezők). A szűrők projektenként menthetők.
- A **Keresés** szavakat keres a címekben és a tartalomban. A `/` billentyű a keresőmezőre ugrik.
- Az **Összetett keresés** (a Keresés oldal gombja) blokkokból épít keresést: szavak vagy reguláris kifejezés, fajták és állapotok, ÉS/VAGY kapcsolattal és csoportokkal. Az ÉS erősebben köt, mint a VAGY; ezen csoporttal lehet változtatni. A szavak töve alapján keres (az `import` megtalálja az `importing`-ot), és minden szónak szerepelnie kell. A túl lassú reguláris kifejezést leállítja, és az oldal jelzi, hogy az eredmény hiányos. A keresés a címben van, ezért könyvjelzőzhető.
- A listán több elemet kijelölve egy lépésben módosíthatja az állapotukat, címkéiket vagy ágaikat, illetve törölheti vagy visszaállíthatja őket.

## Áttekintés, idő és diagramok {#overview}

- Az Áttekintés állapotonkénti számlálókat, az összes becsült és eltöltött időt, állapotdiagramot, a becsült és eltöltött időt összehasonlító diagramot, a legutóbbi elemeket, és ha be van kapcsolva, az aktív ügynöki munkameneteket mutatja.

## MI-ügynökök, munkamenetek és élő frissítések {#agents}

- Az ügynök egy elemen **munkamenetet** indít céllal, haladási megjegyzéseket fűz hozzá, és összegzéssel lezárja. A munkamenetek az Áttekintésen, az elemen és a tábla kisalkalmazásában láthatók.
- **Élő frissítések:** a megnyitott oldalak követik a máshol végzett módosításokat. A felső sávi jelző mutatja, hogy az oldal naprakész-e. A szerkesztés alatt álló űrlapot soha nem írja felül; helyette értesítés kínálja a módosítást. A működést a Beállításokban adhatja meg.

## Beállítások {#settings}

- **Megjelenés:** színek a világos és a sötét témához, alapszínekre való visszaállítással.
- **Megjelenítés** és **Követési alapértékek:** az alapértelmezett nyelv és téma, valamint az új elemek alapértelmezett becsült ideje.
- **Ügynöki munkamenetek kisalkalmazás** és **Élő frissítések:** mi látszik, és hogyan követik az oldalak a módosításokat.
- **Navigáció:** mely importeszközök (*GitHub-import*, *Importtörténet*, *Fájlimport*) jelenjenek meg a bal oldali panelen. Alapértelmezés szerint ki vannak kapcsolva; az oldalak továbbra is elérhetők a címükön.
- **GitHub-exportok:** a tároló, az ág, a mappa és a tokent tartalmazó környezeti változó neve (lásd: [Importálás és exportálás](#import-export)).
- **Projekt:** a projekt neve és leírása.
- **Hozzáférési tokenek:** tokenek létrehozása, átnevezése, hatókörük (`read`, `agent`, `admin`) módosítása, újragenerálása és törlése; a kiszolgáló konfigurációjának tokenjei is megjeleníthetők és újragenerálhatók. Token újragenerálása után frissítse az azt használó összes klienst.
- **Naplózás:** a beállítások minden módosítása, titkos értékek nélkül.

## Importálás és exportálás {#import-export}

- A **Fájlimport** CSV, JSON és Markdown feladatlistákat olvas be. A **GitHub-import** egy GitHub-tároló hibáit importálja. Az **Importtörténet** a korábbi importokat sorolja fel. Ez a három menüpont akkor látszik a bal oldali panelen, ha a Beállításokban be van kapcsolva.
- **Pillanatképek:** a *Pillanatkép exportálása* ZIP-fájlt ír. A *Pillanatkép importálása* pontos előnézet után projektet hoz létre pillanatképből, vagy frissít egyet; a mindkét helyen meglévő elemeknél kiválaszthatja, hogy a projekt változata marad, a pillanatképé lép életbe ha újabb, vagy mindig a pillanatképé. A projektből soha nem törlődik semmi.
- **GitHub-tároló:** a *GitHub* oldal egy projektet egyszerű fájlokként exportál egy tárolóba, exportonként egy committal, és onnan vissza is importál. Előbb hozzon létre egy privát tárolót, és a tartalmához olvasási és írási joggal rendelkező tokent tegyen a Beállításokban megadott környezeti változóba (alapértelmezés: `GITHUB_PAT`). Az oldal munka közben minden lépést megmutat, és nem töltődik újra.
- Ugyanezek a funkciók a parancssorban is megvannak: `issuedeck export-audit-bundle`, `import-audit-bundle`, `github-test`, `github-list`, `github-export`, `github-import`.

## Billentyűparancsok {#shortcuts}

A billentyűparancsok akkor működnek, ha a fókusz nem szövegmezőben van.

| Billentyű | Művelet |
| --- | --- |
| `/` | A keresőre ugrik |
| `n` | Új elem az aktuális projektben |
| `f` | A lista szűrőinek megjelenítése vagy elrejtése |
| `j` / `k` | Következő / előző elem |
| `g`, majd `h` | Az áttekintésre ugrik |
| `g`, majd `l` | A listára ugrik |
| `g`, majd `k` | A Kanban táblára ugrik |
| `g`, majd `s` | A keresőoldalra ugrik |

## MI-ügynök csatlakoztatása {#mcp}

- Az MI-ügynök a MyIssueDeck-kel az **MCP-kiszolgálón** keresztül dolgozik: `python -m issuedeck.mcp` az `ISSUEDECK_BASE_URL` (például `http://127.0.0.1:8766`) és az `ISSUEDECK_TOKEN` (`agent` hatókörű token) környezeti változókkal.
- Vegye fel az ügynök konfigurációjába (például `.mcp.json`) `issuedeck` nevű stdio-kiszolgálóként, indítsa újra az ügynököt, és ellenőrizze, hogy megjelennek-e az eszközök.
- Jó rutin: keresse meg a projektet, hozza létre vagy keresse meg az elemet, indítson munkamenetet, rögzítse a haladást és az eltöltött időt, és adja ki az elemet, ha kész.
- A kiszolgálónak futnia kell. A részleteket a `docs` mappa tartalmazza (MCP Client Setup, Agent Work Sessions).
- Lépésenkénti útmutatók, mindegyikhez egy prompt, amely megtanítja az ügynöknek, hogyan dolgozzon ezzel a nyilvántartóval: [Claude](#claude) és [Codex](#codex).

## A MyIssueDeck használata Claude-dal {#claude}

A Claude Code (a parancssor és a szerkesztőbővítmények) és a Claude Desktop az MCP-kiszolgálón keresztül tud dolgozni ezzel a nyilvántartóval. Ez a rész megmutatja, hogyan kell őket összekötni, milyen eszközöket kapnak, hogyan kell a Claude-nak dolgoznia, és ad egy promptot, amely megtanítja neki a munkamódszert.

### A Claude összekötése {#claude-connect}

- Mielőtt hozzákezd: a kiszolgáló fut, és van `agent` hatókörű tokenje (Beállítások). Ezzel a hatókörrel a Claude olvashatja és írhatja az elemeket, de nem tud belépni az irányítópultra. Kell még az MCP-kiszolgálót elindító parancs: a telepített példánynál `<telepítési mappa>\.venv\Scripts\python.exe -m issuedeck.mcp`, a forráskönyvtárnál `uv --directory <mappa> run python -m issuedeck.mcp`.
- Claude Code: a projekt mappájában futtassa ezt: `claude mcp add --env ISSUEDECK_BASE_URL=http://127.0.0.1:8765 --env ISSUEDECK_TOKEN=<az-On-tokenje> --transport stdio issuedeck -- <a fenti parancs>`. A `--transport stdio` maradjon az utolsó `--env` és a név között, különben a nevet változónak olvassa. A `--scope project` a kiszolgálót a `.mcp.json` fájlba írja, amelyet a verziókezelő megoszt: a tokent ne írja ide, hanem írja ezt: `"ISSUEDECK_TOKEN": "${ISSUEDECK_TOKEN}"`, és állítsa be a változót a környezetében. A `--scope user` minden projektjében elérhetővé teszi a kiszolgálót.
- Ellenőrzés: a `claude mcp list` működő kiszolgálónál `Connected` állapotot mutat, ugyanezt mutatja a `/mcp` a Claude Codeban. A `.mcp.json` kiszolgálója először a jóváhagyására vár: futtassa a `claude` parancsot a mappában, és hagyja jóvá. Ha az eszközök nem jelennek meg, indítson új Claude Code munkamenetet.
- Claude Desktop: nyissa meg a Settings, Developer, Edit Config pontot. A fájl a `claude_desktop_config.json` (Windows: `%APPDATA%\Claude`, macOS: `~/Library/Application Support/Claude`, Linux: `~/.config/Claude`). Vegye fel a kiszolgálót az `mcpServers` alá `command`, `args` és `env` mezőkkel, mentse, majd lépjen ki teljesen a Claude Desktopból, és indítsa újra. Példa a `docs/mcp-clients.md` fájlban van.
- Hová kerül a tanító prompt: a Claude Code minden munkamenet elején beolvassa a projekt mappájában lévő `CLAUDE.md` fájlt (a `~/.claude/CLAUDE.md` minden projektre vonatkozik, a `CLAUDE.local.md` csak Önre). Legyen rövid, legfeljebb nagyjából 200 sor. A Claude Desktopnak nincs ilyen fájlja: illessze be a promptot a beszélgetés elején.
- Ezek a lépések az eszközök dokumentációját követik, 2026-11-27-én ellenőrizve. Az eszközök változnak: ha egy parancsot elutasít, nézze meg az eszköz saját dokumentációját.

### Mit tud a Claude {#claude-tools}

A Claude 29 eszközt kap az MCP-kiszolgálótól:

| Csoport | Eszközök |
|---|---|
| Projektek | `list_projects`, `get_project_config` |
| Elemek | `create_item`, `get_item`, `update_item`, `bulk_update_items`, `delete_item`, `list_items`, `search_items`, `append_item_event`, `ship_item` |
| Kapcsolatok | `add_relationship`, `remove_relationship` |
| Munkamenetek | `start_work_session`, `update_work_session`, `finish_work_session`, `get_work_session`, `list_work_sessions` |
| Képek (SVG) | `upload_image`, `upload_image_data`, `list_images`, `get_image`, `delete_image` |
| Dokumentumok (Markdown) | `create_document`, `get_document`, `list_documents`, `update_document`, `delete_document`, `list_document_revisions` |

### Hogyan dolgozzon a Claude {#claude-method}

A Claude kövesse az elem életciklusát, hogy a tábla és az elem oldala mindig a valós állapotot mutassa:

1. Indítás: `start_work_session` céllal, majd az elem legyen `in_progress`.
2. Közben: `update_work_session` minden fontos lépésnél. Ha Önre kell várnia, az elem legyen `blocked`, és írja le az okot.
3. Minden szakasz végén: `finish_work_session` összefoglalóval, majd az elemen frissítse az összes `time_spent` értéket, és az elem szövegének végére írjon haladási jegyzetet.
4. Az utolsó szakasz végén: az elem legyen `ready_to_ship`.
5. Miután a változás be van commitolva és kiadva: `ship_item`; az elem `done` lesz.

Továbbá: létrehozás előtt nézzen körül, minden új elemen adja meg az `estimated_time` értéket, a megemlített elemeket kapcsolja össze (related), és soha ne hagyjon aktív munkamenetet (a be nem fejezett munkamenet tovább látszik a tábla moduljában).

### Példa prompt a Claude-hoz {#claude-prompt}

Másolja ezt a szöveget a projektje `CLAUDE.md` fájljába (vagy illessze be a beszélgetés elején), és a `<project-key>` helyére írja a projektje kulcsát. Bármilyen nyelven működik, amelyen a Claude-dal beszél. Ugyanez a szöveg a `docs/agent-prompts/claude-prompt.md` fájlban is megvan.

```text
# MyIssueDeck: how you track work in this project

The issue tracker of this project is MyIssueDeck. You reach it through the MCP server "issuedeck".
My project key is <project-key>.

## First steps
1. Call list_projects, then get_project_config for <project-key>. Use only the kinds, statuses and tags it lists.
2. If the issuedeck tools are missing, or a call fails with 401 (token) or 404 (project key), stop and tell me. Do not work around it.
3. The life cycle below names the statuses proposed, in_progress, blocked, ready_to_ship and done. If the project has no status with one of these names, use the closest one it lists and tell me which.

## Finding and creating items
- Look before you create: search_items and list_items (filters: kind, status, tag). Do not create duplicates.
- create_item: pick a kind from the project config, write a short title, put the requirement in the body, and always set the custom field estimated_time (hours).
- When I mention another item, link it with add_relationship (related_to).
- Never rewrite text I wrote. Add to it with append_body in update_item.

## The life cycle of an item you work on
The status changes at the moment the event happens, never afterwards.
1. Start (of the item and of every phase): start_work_session (goal = what this phase does), then update_item with status in_progress.
2. During: update_work_session for decisions, defects found and test results. If you must wait for me: update_item with status blocked and append why to the body; set in_progress again when it is solved.
3. End of every phase: finish_work_session with a summary (what was done, the tests, what you did not verify); then update_item with the custom field time_spent (total hours so far) and a progress note appended to the body. Never leave a session active when you stop.
4. End of the last phase: update_item with status ready_to_ship and a note of what is left to check.
5. After the change is committed and released: ship_item (branch, version, commit ids). The status becomes done.

## Documents and images
- Prompts, requests and reports are kept as documents: create_document, get_document, list_documents, update_document, delete_document, list_document_revisions.
- To change a document: get_document first, then update_document with the revision you read. On a conflict, read it again and merge; never overwrite another person's change. To add a line, use update_document with append_body.
- SVG diagrams are kept with upload_image, list_images, get_image and delete_image. Show an image in an item text with ![name](image:IMG-0001).

## Never, unless I ask you
- Commit, tag, push, or change configuration, tokens or other projects' items.
- Delete items, documents or images.
- Put a token or any other secret into an item, a document or a message.
```

### Ha nem működik {#claude-problems}

- Hiányoznak az eszközök: a `claude mcp list` az `issuedeck` kiszolgálót csatlakozottnak kell mutassa. Ellenőrizze a parancs útvonalát és hogy a kiszolgáló fut-e, és indítson új Claude Code munkamenetet (Claude Desktop: lépjen ki teljesen, és indítsa újra).
- A hívás 401-gyel hibázik: a token rossz, vagy nincs `agent` hatóköre. 404 esetén a projektkulcs rossz.
- A dokumentum módosítása ütközéssel hibázik: közben valaki módosította; olvassa be újra, és egyesítse.

## A MyIssueDeck használata Codexszel {#codex}

A Codex (a parancssori kliens és az IDE-bővítmény) ugyanazon az MCP-kiszolgálón keresztül tud dolgozni ezzel a nyilvántartóval. Az összeköttetést a Codex konfigurációs fájljába kell írni, az állandó utasításokat a Codex az `AGENTS.md` fájlból olvassa.

### A Codex összekötése {#codex-connect}

- Mielőtt hozzákezd: ugyanaz a futó kiszolgáló, ugyanaz az `agent` token és ugyanaz a parancs, mint a Claude-nál.
- Vegye fel a kiszolgálót így: `codex mcp add issuedeck --env ISSUEDECK_BASE_URL=http://127.0.0.1:8765 --env ISSUEDECK_TOKEN=<az-On-tokenje> -- <a Claude-részben szereplő parancs>`, vagy írja a konfigurációs fájlba az alább látható módon.
- A fájl a `config.toml` a Codex saját mappájában (alapértelmezés szerint `~/.codex`; a dokumentáció nem ad külön Windows-útvonalat), vagy egy megbízott projekt `.codex/config.toml` fájlja. A parancssori kliens és az IDE-bővítmény közösen használja. Hogy a token ne kerüljön a fájlba, írja be a nevét az `env_vars` listába, és a változót állítsa be a környezetében az érték beírása helyett (e kulcs dokumentációját csak összefoglalóban lehetett olvasni).
- Ellenőrzés: `codex mcp list`, vagy `/mcp` a terminálfelületen. Az IDE-bővítményben a fájl mentése után indítsa újra a bővítményt.
- A Codex jóváhagyást kérhet, mielőtt egy eszközt meghív. Ennek beállítása (`default_tools_approval_mode`, egy eszközre `tools.<eszköz>.approval_mode`) a Codex dokumentációjában van leírva.
- Hová kerül a tanító prompt: a Codex az `AGENTS.md` fájlt olvassa (`~/.codex/AGENTS.md` minden projektre; a projektben a projekt gyökerétől az aktuális mappáig, mappánként egy fájl, a közelebbiek később). Az együttes méret korlátozott, alapértelmezés szerint 32 KiB.
- Ezek a lépések a Codex dokumentációját követik, 2026-11-27-én ellenőrizve. Ha egy parancsot elutasít, nézze meg a saját dokumentációját.

```toml
[mcp_servers.issuedeck]
command = 'C:\Utility\MyIssueDeck\.venv\Scripts\python.exe'
args = ["-m", "issuedeck.mcp"]
env_vars = ["ISSUEDECK_TOKEN"]

[mcp_servers.issuedeck.env]
ISSUEDECK_BASE_URL = "http://127.0.0.1:8765"
```

### Mit tud a Codex {#codex-tools}

A Codex ugyanazt a 29 eszközt kapja, mint a Claude: lásd [Mit tud a Claude](#claude-tools). Ugyanazt a munkamódszert követi.

### Példa prompt a Codexhez {#codex-prompt}

Másolja ezt a szöveget a projektje `AGENTS.md` fájljába (vagy illessze be a munkamenet elején), és a `<project-key>` helyére írja a projektje kulcsát. Bármilyen nyelven működik, amelyen a Codexszel beszél. Ugyanez a szöveg a `docs/agent-prompts/codex-prompt.md` fájlban is megvan.

```text
# MyIssueDeck: how you track work in this project

The issue tracker of this project is MyIssueDeck. You reach it through the MCP server "issuedeck".
My project key is <project-key>.

## First steps
1. Call list_projects, then get_project_config for <project-key>. Use only the kinds, statuses and tags it lists.
2. If the issuedeck tools are missing, or a call fails with 401 (token) or 404 (project key), stop and tell me. Do not work around it.
3. The life cycle below names the statuses proposed, in_progress, blocked, ready_to_ship and done. If the project has no status with one of these names, use the closest one it lists and tell me which.
4. If a tool call waits for my approval, wait. If I refuse it, do not try the same call again; tell me what you needed.

## Finding and creating items
- Look before you create: search_items and list_items (filters: kind, status, tag). Do not create duplicates.
- create_item: pick a kind from the project config, write a short title, put the requirement in the body, and always set the custom field estimated_time (hours).
- When I mention another item, link it with add_relationship (related_to).
- Never rewrite text I wrote. Add to it with append_body in update_item.

## The life cycle of an item you work on
The status changes at the moment the event happens, never afterwards.
1. Start (of the item and of every phase): start_work_session (goal = what this phase does), then update_item with status in_progress.
2. During: update_work_session for decisions, defects found and test results. If you must wait for me: update_item with status blocked and append why to the body; set in_progress again when it is solved.
3. End of every phase: finish_work_session with a summary (what was done, the tests, what you did not verify); then update_item with the custom field time_spent (total hours so far) and a progress note appended to the body. Never leave a session active when you stop.
4. End of the last phase: update_item with status ready_to_ship and a note of what is left to check.
5. After the change is committed and released: ship_item (branch, version, commit ids). The status becomes done.

## Documents and images
- Prompts, requests and reports are kept as documents: create_document, get_document, list_documents, update_document, delete_document, list_document_revisions.
- To change a document: get_document first, then update_document with the revision you read. On a conflict, read it again and merge; never overwrite another person's change. To add a line, use update_document with append_body.
- SVG diagrams are kept with upload_image, list_images, get_image and delete_image. Show an image in an item text with ![name](image:IMG-0001).

## Never, unless I ask you
- Commit, tag, push, or change configuration, tokens or other projects' items.
- Delete items, documents or images.
- Put a token or any other secret into an item, a document or a message.
```

### Ha nem működik {#codex-problems}

- Hiányoznak az eszközök: a `codex mcp list` listájában szerepelnie kell az `issuedeck` kiszolgálónak. Ellenőrizze a parancs útvonalát és hogy a kiszolgáló fut-e; az IDE-bővítményben indítsa újra a bővítményt.
- A hívás 401-gyel hibázik: a token rossz, vagy nincs `agent` hatóköre; 404 esetén a projektkulcs rossz.
- Egy hívás jóváhagyásra vár: a Codex az eszköz használata előtt rákérdez; hagyja jóvá, vagy változtassa meg a jóváhagyási beállítást a konfigurációban.

## Hibaelhárítás {#troubleshooting}

- **Nem tud bejelentkezni:** használjon `admin` hatókörű tokent; a tokent egy működő munkamenet Beállítások oldalán vagy a kiszolgáló konfigurációjában ellenőrizheti.
- **Egy oldal nem frissül magától:** nézze meg a kapcsolatjelzőt; az élő frissítések a Beállításokban kikapcsolhatók.
- **A GitHub-export sikertelen:** az üzenet megnevezi az okot (nincs beállítva a tokenváltozó, a tokennek nincs írási joga, nyilvános tároló, közben megváltozott az ág, korlát). Használja a Beállítások *Kapcsolat tesztelése* gombját.
- **További dokumentáció:** a szoftver `docs` mappája, valamint a `README`.
