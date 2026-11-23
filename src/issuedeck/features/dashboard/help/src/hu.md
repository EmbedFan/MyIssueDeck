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

## Hibaelhárítás {#troubleshooting}

- **Nem tud bejelentkezni:** használjon `admin` hatókörű tokent; a tokent egy működő munkamenet Beállítások oldalán vagy a kiszolgáló konfigurációjában ellenőrizheti.
- **Egy oldal nem frissül magától:** nézze meg a kapcsolatjelzőt; az élő frissítések a Beállításokban kikapcsolhatók.
- **A GitHub-export sikertelen:** az üzenet megnevezi az okot (nincs beállítva a tokenváltozó, a tokennek nincs írási joga, nyilvános tároló, közben megváltozott az ág, korlát). Használja a Beállítások *Kapcsolat tesztelése* gombját.
- **További dokumentáció:** a szoftver `docs` mappája, valamint a `README`.
