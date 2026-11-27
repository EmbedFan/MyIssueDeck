"""Hungarian (hu) dashboard messages.

Every key of the English dictionary in ``i18n.py`` must exist here; the test
suite checks this. Placeholders such as ``{count}`` must stay exactly as in
English.
"""

MESSAGES_HU: dict[str, str] = {
    "activity.add": "Megjegyzés hozzáadása",
    "activity.empty": "Még nincs tevékenység",
    "activity.placeholder": "Döntések, ellenőrzési eredmények vagy átadási jegyzetek rögzítése...",
    "activity.title": "Tevékenység",
    "activity.count_suffix": "elem",
    "aria.breadcrumbs": "Navigációs útvonal",
    "aria.close_sidebar": "Oldalsáv bezárása",
    "aria.main_nav": "Fő navigáció",
    "aria.search": "Keresés",
    "aria.saved_filters": "Mentett szűrők",
    "aria.toggle_sidebar": "Oldalsáv váltása",
    "aria.work_queues": "Munkasorok",
    "auth.invalid_token": "Érvénytelen token.",
    "auth.login_title": "Bejelentkezés az irányítópultra",
    "auth.sign_in": "Bejelentkezés",
    "auth.token": "API-token",
    "bulk.action": "Művelet",
    "bulk.action_delete": "törlés",
    "bulk.action_restore": "visszaállítás",
    "bulk.action_update": "frissítés",
    "bulk.apply": "Alkalmazás",
    "bulk.custom_fields": "Egyéni mezők",
    "bulk.error.none_selected": "Először válasszon ki legalább egy elemet.",
    "bulk.keep_branches": "Ágak megtartása",
    "bulk.keep_custom_field": "Változatlanul hagyás",
    "bulk.keep_kind": "Típus megtartása",
    "bulk.keep_status": "Állapot megtartása",
    "bulk.replace_branches": "Ágak cseréje",
    "bulk.select_all": "Az összes látható elem kiválasztása",
    "bulk.select_item": "{id} kiválasztása",
    "bulk.success": "A tömeges {action} {count} elemen alkalmazva.",
    "bulk.tag_add": "Hozzáadás",
    "bulk.tag_remove": "Eltávolítás",
    "bulk.tag_replace": "Csere",
    "chart.count": "Darabszám",
    "chart.estimated_time": "Becsült idő (óra)",
    "chart.time_spent": "Ráfordított idő (óra)",
    "common.add": "Hozzáadás",
    "common.back": "Vissza",
    "common.back_to_list": "Vissza a listához",
    "common.any": "Bármelyik",
    "common.branch": "Ág",
    "common.branches": "Ágak",
    "common.cancel": "Mégse",
    "common.content": "Tartalom",
    "common.create": "Létrehozás",
    "common.created_at": "Létrehozva",
    "common.delete": "Törlés",
    "common.deleted": "Törölve",
    "common.edit": "Szerkesztés",
    "common.empty_body": "Nincs tartalom",
    "common.filter": "Szűrés",
    "common.id": "ID",
    "common.items_suffix": "elem",
    "common.kind": "Típus",
    "common.load_more": "Továbbiak betöltése",
    "common.no": "Nincs",
    "common.no_branches": "Nincs ág",
    "common.no_value": "Nem",
    "common.no_items": "Még nincs elem",
    "common.no_matching_items": "Nincs egyező elem",
    "common.no_tags": "Nincs címke",
    "common.next": "Következő",
    "common.preview": "Előnézet",
    "common.previous": "Előző",
    "common.reset": "Alaphelyzet",
    "common.restore": "Visszaállítás",
    "common.save": "Mentés",
    "common.ship": "Kiadás",
    "common.show_deleted": "Törölt elemek mutatása",
    "common.status": "Állapot",
    "common.tags": "Címkék",
    "common.title": "Cím",
    "common.updated": "Frissítve",
    "common.updated_at": "Frissítve",
    "common.version": "Verzió",
    "common.yes": "Igen",
    "confirm.delete_item": "Biztosan törli ezt az elemet?",
    "confirm.delete_relationship": "Biztosan törli ezt a kapcsolatot?",
    "confirm.delete_saved_filter": "Biztosan törli ezt a mentett szűrőt?",
    "external_links.empty": "Még nincsenek külső hivatkozások",
    "external_links.github_commit": "GitHub commit",
    "external_links.github_issue": "GitHub issue",
    "external_links.github_pr": "GitHub PR",
    "external_links.other": "Külső hivatkozás",
    "external_links.title": "Külső hivatkozások",
    "export.audit_bundle": "Pillanatkép exportálása",
    "form.body_help": "Markdown támogatott",
    "form.body_placeholder": "Markdown formátum támogatott",
    "form.create_item": "Elem létrehozása",
    "form.custom_fields": "Egyéni mezők",
    "custom_fields.false": "Nem",
    "custom_fields.filters": "Egyéni mezők",
    "custom_fields.max": "Maximum",
    "custom_fields.min": "Minimum",
    "custom_fields.missing": "Nincs érték",
    "custom_fields.presence": "Megléte",
    "custom_fields.present": "Van érték",
    "custom_fields.true": "Igen",
    "form.done_requires_ship": "A „Kész” állapotot az elem kiadásával kell beállítani.",
    "form.edit_item": "Elem szerkesztése",
    "form.saved": "Mentve",
    "form.save_failed": "A mentés nem sikerült",
    "form.empty_preview": "Nincs megjeleníthető tartalom",
    "form.external_links": "Külső hivatkozások",
    "form.external_links_help": (
        "Soronként egy URL; egyedi címkéhez használja a Címke | URL formát."
    ),
    "form.external_links_placeholder": "https://github.com/org/repo/issues/42",
    "form.tags_help": "Több címkét vesszővel válasszon el",
    "form.tags_placeholder": "Vesszővel elválasztva, például: hiba, frontend, sürgős",
    "form.title_placeholder": "Adja meg az elem címét",
    "home.kind_distribution": "Típusok megoszlása",
    "home.no_items": "Még nincs elem",
    "home.recent_activity": "Legutóbbi tevékenység",
    "home.status_distribution": "Állapotok megoszlása",
    "home.time_overview": "Becsült és ráfordított idő állapotonként",
    "home.time_overview_empty": (
        "Még nincs rögzített idő. Állítson be becsült vagy ráfordított időt "
        "az elemekhez, hogy megjelenjen ez a diagram."
    ),
    "home.work_sessions_empty": "Nincs aktív ügynöki munkamenet",
    "home.work_sessions_title": "Aktív ügynöki munkamenetek",
    "language.en": "EN",
    "language.hu": "Magyar",
    "language.label": "Nyelv",
    "settings.navigation.title": "Navigáció",
    "settings.navigation.help": (
        "Válassza ki, mely importáló eszközök jelenjenek meg a bal oldali panelen. "
        "Az oldalak továbbra is elérhetők a címükön."
    ),
    "settings.navigation.show": "Megjelenítés a bal oldali panelen:",
    "language.apply": "Alkalmaz",
    "nav.help": "Súgó",
    "help.title": "Súgó",
    "help.print": "Nyomtatás",
    "help.version": "Verzió: {version}",
    "help.fallback": "Ez a súgó még nem érhető el az Ön nyelvén; az angol szöveg látható.",
    "language.zh": "中文",
    "data_import.batch_tag": "Kötegcímke",
    "data_import.checked_tasks": "Kipipálva",
    "data_import.default_status": "Alapértelmezett állapot",
    "data_import.default_status_auto": "Automatikus",
    "data_import.default_status_help": "CSV- és JSON-sorokhoz, amelyekben nincs állapot.",
    "data_import.description": (
        "CSV, JSON vagy Markdown feladatlisták importálása ebbe a projektbe."
    ),
    "data_import.dry_run": "Importálás előnézete",
    "data_import.error.empty_file": "Válasszon egy nem üres forrásfájlt.",
    "data_import.error.invalid_type": "Az importtípus CSV, JSON vagy Markdown lehet.",
    "data_import.error_title": "Az importálás sikertelen",
    "data_import.external_links": "Hivatkozások",
    "data_import.custom_fields": "Egyéni mezők",
    "data_import.field_aliases": "Mezőnevek megfeleltetése",
    "data_import.field_aliases_help": (
        "Opcionális CSV/JSON-megfeleltetések, soronként egy MEZŐ=alias[,alias...] "
        "formában. Projekt egyéni mezőinek megfeleltetéséhez használja a "
        "custom.priority=Priority formát."
    ),
    "data_import.import": "Elemek importálása",
    "data_import.include_checked": "Kipipált Markdown-feladatok belefoglalása",
    "data_import.objects_found": "Objektumok",
    "data_import.objects_skipped": "Kihagyva",
    "data_import.planned": "Tervezett",
    "data_import.presets": "Sablonok",
    "data_import.presets_help": "Opcionális CSV/JSON-sablonok: github, jira, linear, generic.",
    "data_import.result_dry_run": "előnézet",
    "data_import.result_empty": "Futtasson előnézetet, hogy lássa, mi jön létre.",
    "data_import.result_import": "importálva",
    "data_import.result_title": "Importálási összesítő",
    "data_import.rows_found": "Sorok",
    "data_import.rows_skipped": "Kihagyva",
    "data_import.skipped_checked": "Kihagyott kipipáltak",
    "data_import.source_file": "Forrásfájl",
    "data_import.source_type": "Formátum",
    "data_import.status_mapped": "Megfeleltetett állapot",
    "data_import.status_maps": "Állapot-megfeleltetés",
    "data_import.status_maps_help": (
        "Opcionális CSV/JSON-megfeleltetések, soronként egy FORRÁS=CÉL formában."
    ),
    "data_import.tags_help": "Az összes importált elemhez adott további IssueDeck-címkék.",
    "data_import.tasks_found": "Feladatok",
    "data_import.title": "Fájlok importálása",
    "data_import.triage_import": "Az importálás áttekintése",
    "data_import.triage_import_help": (
        "Megnyitja a listát, szűrve az ezzel az importtal írt elemekre."
    ),
    "data_import.type_csv": "CSV",
    "data_import.type_json": "JSON",
    "data_import.type_markdown": "Markdown",
    "data_import.view_items": "Elemek megtekintése",
    "data_import.written": "Írva",
    "github_import.default_status": "Alapértelmezett állapot",
    "github_import.default_status_auto": "Automatikus",
    "github_import.batch_tag": "Kötegcímke",
    "github_import.description": (
        "Repozitórium-hibák importálása ebbe a projektbe, az importálás előnézete, "
        "majd csak az új elemek írása."
    ),
    "github_import.dry_run": "Importálás előnézete",
    "github_import.error.invalid_state": (
        "A GitHub-hibák állapota open, closed vagy all lehet."
    ),
    "github_import.error_title": "Az importálás sikertelen",
    "github_import.existing_skipped": "Meglévő",
    "github_import.external_links": "Hivatkozások",
    "github_import.fetched": "Lekérve",
    "github_import.github_token": "GitHub-token",
    "github_import.github_token_help": (
        "Nyilvános repozitóriumokhoz nem kötelező; privát repozitóriumokhoz vagy "
        "magasabb lekérési korláthoz szükséges."
    ),
    "github_import.import": "Hibák importálása",
    "github_import.include_pulls": "Pull requestek belefoglalása",
    "github_import.labels": "GitHub-címkék",
    "github_import.labels_help": "Vesszővel vagy új sorral elválasztva. Üresen minden címke.",
    "github_import.limit": "Korlát",
    "github_import.planned": "Tervezett",
    "github_import.pulls_skipped": "Kihagyott PR-ok",
    "github_import.repo": "Repozitórium",
    "github_import.repo_help": (
        "Használja az owner/repo formátumot vagy a github.com repozitórium URL-jét."
    ),
    "github_import.result_dry_run": "előnézet",
    "github_import.result_empty": "Futtasson előnézetet, hogy lássa, mi jön létre.",
    "github_import.result_import": "importálva",
    "github_import.result_title": "Importálási összesítő",
    "github_import.state": "Állapot",
    "github_import.state_all": "Mind",
    "github_import.state_closed": "Lezárt",
    "github_import.state_open": "Nyitott",
    "github_import.status_mapped": "Megfeleltetett állapot",
    "github_import.status_maps": "Állapot-megfeleltetés",
    "github_import.status_maps_help": "Soronként egy FORRÁS=CÉL megfeleltetés.",
    "github_import.tags_help": "Az összes importált elemhez adott további IssueDeck-címkék.",
    "github_import.title": "GitHub-hibák importálása",
    "github_import.triage_import": "Az importálás áttekintése",
    "github_import.triage_import_help": (
        "Megnyitja a listát, szűrve az ezzel az importtal írt elemekre."
    ),
    "github_import.view_items": "Elemek megtekintése",
    "github_import.written": "Írva",
    "import_history.active_items": "Aktív",
    "import_history.batch_tag": "Kötegcímke",
    "import_history.confirm_delete_batch": (
        "Az összes aktív elemet puhán törli ebből az importkötegből?"
    ),
    "import_history.confirm_restore_batch": (
        "Visszaállítja az importköteg összes törölt elemét?"
    ),
    "import_history.delete_batch": "Köteg puha törlése",
    "import_history.delete_empty": "Ehhez az importkötegkhez nincsenek aktív elemek.",
    "import_history.delete_missing": "Ez az importköteg nem található.",
    "import_history.delete_success": "{count} elem puhán törölve az importkötegből.",
    "import_history.description": (
        "Tekintse át a legutóbbi importokat, és nyissa meg újra a szűrt áttekintő nézeteket."
    ),
    "import_history.empty_body": (
        "Futtasson GitHub- vagy fájlimportot az első köteg létrehozásához."
    ),
    "import_history.empty_title": "Nincs rögzített import",
    "import_history.deleted_items": "Törölve",
    "import_history.external_links": "Hivatkozások",
    "import_history.filter_source": "Forrás",
    "import_history.filter_state": "Állapot",
    "import_history.pagination_summary": (
        "{start}–{end} megjelenítve, összesen {total} legutóbbi találat."
    ),
    "import_history.planned": "Tervezett",
    "import_history.restore_batch": "Köteg visszaállítása",
    "import_history.restore_empty": "Ehhez az importkötegkhez nincsenek törölt elemek.",
    "import_history.restore_missing": "Ez az importköteg nem található.",
    "import_history.restore_success": "{count} elem visszaállítva az importkötegből.",
    "import_history.skipped": "Kihagyva",
    "import_history.source_all": "Minden forrás",
    "import_history.source_csv": "CSV",
    "import_history.source_github": "GitHub",
    "import_history.source_json": "JSON",
    "import_history.source_markdown": "Markdown",
    "import_history.state_active": "Van aktív elem",
    "import_history.state_all": "Minden állapot",
    "import_history.state_deleted": "Teljesen törölve",
    "import_history.state_mixed": "Aktív és törölt",
    "import_history.status_mapped": "Megfeleltetett állapot",
    "import_history.title": "Importtörténet",
    "import_history.triage_batch": "Köteg áttekintése",
    "import_history.written": "Írva",
    "nav.overview": "Áttekintés",
    "nav.kanban": "Kanban",
    "nav.list": "Lista",
    "nav.search": "Keresés",
    "nav.images": "Képek",
    "nav.documents": "Dokumentumok",
    "documents.title": "Dokumentumok",
    "documents.description": (
        "A projekt Markdown dokumentumai: promptok, leírások, kérések és jelentések. "
        "Minden mentés változatként megmarad (az utolsó 50)."
    ),
    "documents.stored": "Tárolva: {names}",
    "documents.deleted": "{name} törölve.",
    "documents.refused": "Nem lett tárolva - {name}: {message}",
    "documents.exists": (
        "Nem lett tárolva - {name}: már van ilyen nevű dokumentum. "
        "Töltse fel újra, és erősítse meg a cserét."
    ),
    "documents.no_file": "Válasszon ki legalább egy fájlt.",
    "documents.replace_confirm": (
        "Már van {names} nevű dokumentum. Lecseréli egy új változattal?"
    ),
    "documents.choose": "Markdown fájlok kiválasztása",
    "documents.kind": "Fajta",
    "documents.kind_prompt": "Prompt",
    "documents.kind_description": "Leírás",
    "documents.kind_request": "Kérés",
    "documents.kind_report": "Jelentés",
    "documents.kind_other": "Egyéb",
    "documents.upload": "Feltöltés",
    "documents.upload_hint": (
        "Bármilyen Markdown fájl; a fájlneve lesz a dokumentum neve. "
        "A nem szöveges (bináris) fájlt elutasítjuk."
    ),
    "documents.usage": "{count} dokumentum",
    "documents.empty": "Még nincs dokumentum.",
    "documents.name": "Név",
    "documents.updated": "Módosítva",
    "documents.revision": "Változat",
    "documents.size": "Méret",
    "documents.actor": "Ki",
    "documents.edit": "Szerkesztés",
    "documents.download": "Letöltés",
    "documents.delete": "Törlés",
    "documents.delete_confirm": (
        "Törli a(z) {name} dokumentumot? Minden változata is törlődik. Ez nem vonható vissza."
    ),
    "documents.back": "Vissza a dokumentumokhoz",
    "documents.history": "Előzmények",
    "documents.history_title": "{name} előzményei",
    "documents.open": "Megnyitás",
    "documents.restore": "Visszaállítás",
    "documents.current": "jelenlegi",
    "documents.view_current": "A jelenlegi szöveg megnyitása",
    "documents.old_revision": "Ez a(z) {number}. változat. A jelenlegi a(z) {current}.",
    "documents.empty_text": "Ez a dokumentum üres.",
    "documents.title_label": "Cím (nem kötelező)",
    "documents.write": "Írás",
    "documents.revisions_kept": "Az utolsó 50 változat marad meg.",
    "documents.item_title": "Dokumentumok",
    "documents.none_linked": "Nincs hozzákapcsolt dokumentum.",
    "documents.none_available": "A projektnek még nincs dokumentuma.",
    "documents.all_linked": "A projekt minden dokumentuma hozzá van kapcsolva.",
    "documents.choose_to_link": "A projekt egy dokumentumának hozzákapcsolása",
    "documents.link": "Hozzákapcsolás",
    "documents.unlink": "Kapcsolat törlése",
    "documents.linked_to": "{count} elemhez kapcsolva",
    "documents.linked_items": "A dokumentumot hivatkozó elemek",
    "documents.no_linked_items": "Egy elem sem hivatkozza ezt a dokumentumot.",
    "documents.delete_confirm_linked": (
        "Törli a(z) {name} dokumentumot? A(z) {count} elemhez fűződő kapcsolatai megszűnnek, "
        "és minden változata is törlődik. Ez nem vonható vissza."
    ),
    "documents.conflict": (
        "A(z) {name} dokumentumot valaki más módosította (most a(z) {revision}. változat). "
        "A szövege lent megmaradt; a mentés felülírja az újabb szöveget."
    ),
    "images.title": "Képek",
    "images.description": "A projekt SVG képei: feltöltés, letöltés és törlés.",
    "images.upload": "Feltöltés",
    "images.choose": "SVG fájlok kiválasztása",
    "images.drop_hint": "vagy húzza ide az SVG fájlokat",
    "images.empty": "Még nincs kép.",
    "images.download": "Letöltés",
    "images.delete": "Törlés",
    "images.open": "Megnyitás új oldalon",
    "images.delete_confirm": "Törli ezt a képet? Ez nem vonható vissza.",
    "images.uploaded": "Feltöltve: {names}",
    "images.deleted": "{id} törölve.",
    "images.refused": "Nem lett tárolva - {name}: {message}",
    "images.no_file": "Válasszon ki legalább egy SVG fájlt.",
    "images.usage": "{count} kép, {used} felhasználva ennyiből: {limit}",
    "images.max_file": "Legnagyobb fájl: {limit}",
    "images.item_title": "Képek",
    "images.none_linked": "Nincs hozzákapcsolt kép.",
    "images.none_available": "A projektnek még nincs képe.",
    "images.all_linked": "A projekt minden képe hozzá van kapcsolva.",
    "images.choose_to_link": "A projekt egy képének hozzákapcsolása",
    "images.link": "Hozzákapcsolás",
    "images.unlink": "Kapcsolat törlése",
    "images.insert": "Kép beszúrása...",
    "images.reference_hint": "A képet a szövegben így jelenítheti meg: ![név](image:IMG-0001).",
    "images.linked_to": "{count} elemhez kapcsolva",
    "images.delete_confirm_linked": (
        "Törli ezt a képet? A(z) {count} elemhez fűződő kapcsolatai megszűnnek. "
        "Ez nem vonható vissza."
    ),
    "nav.import_github": "GitHub-import",
    "nav.import_history": "Importtörténet",
    "nav.import_files": "Fájlimport",
    "nav.create": "Új",
    "nav.detail": "Részletek",
    "nav.edit": "Szerkesztés",
    "nav.projects": "Projektek",
    "nav.project_setup": "Projektbeállítás",
    "nav.switch_project": "Projektváltás",
    "nav.new_project": "Új projekt",
    "nav.sign_out": "Kijelentkezés",
    "onboarding.no_items_body": "Hozza létre a projekt első követett elemét.",
    "onboarding.no_items_title": "Indítsa el a sort",
    "onboarding.no_projects_body": (
        "Hozzon létre egy projektet, vagy importálja a korábban GitHub-tárolóba exportált "
        "projekteket."
    ),
    "onboarding.import_github": "Importálás GitHubról",
    "onboarding.import_source": "Az import innen olvas: {repository}.",
    "onboarding.no_projects_title": "Még nincs projekt",
    "onboarding.setup_eyebrow": "Kezdje itt",
    "onboarding.setup_title": "Beállítási lista",
    "onboarding.step_project_title": "A projekt kész",
    "onboarding.step_project_body": "Tartsa ezt a munkaterületet elkülönítve a demóadatoktól.",
    "onboarding.step_project_action": "Projekt hozzáadása",
    "onboarding.step_item_title": "Hozzon létre egy elemet",
    "onboarding.step_item_body": "Rögzítsen egy funkciót, hibát vagy fejlesztést.",
    "onboarding.step_item_action": "Új elem",
    "onboarding.step_queue_title": "Nyissa meg a sort",
    "onboarding.step_queue_body": "A napi áttekintéshez használja az aktív nézetet.",
    "onboarding.step_queue_action": "Aktív nézet",
    "onboarding.step_ship_title": "Adjon ki egy elemet",
    "onboarding.step_ship_body": "Rögzítse a verziót és a commitokat, amikor a munka elkészül.",
    "onboarding.step_ship_action": "Kiadási sor",
    "page.kanban.title": "Kanban",
    "page.list.title": "Lista",
    "page.search.title": "Keresés",
    "project_delete.active_sessions": (
        "{count} aktív vagy szüneteltetett munkamenet akadályozza a törlést. "
        "Először fejezze be vagy szakítsa meg őket."
    ),
    "project_delete.backup_note": (
        "Bármi törlése előtt az auditcsomag biztonsági mentése a data/deleted-projects/ "
        "mappába kerül, a projekt konfigurációja pedig a projects/.deleted/ mappába "
        "archiválódik."
    ),
    "project_delete.cancel": "Mégse",
    "project_delete.confirm_button": "Projekt végleges törlése",
    "project_delete.confirm_label": "A megerősítéshez írja be a projektkulcsot: {project_key}",
    "project_delete.deleted_items": "Már törölt elemek",
    "project_delete.download_backup": "Auditcsomag letöltése most",
    "project_delete.error.active_sessions": (
        "A projektben aktív vagy szüneteltetett munkamenetek vannak. Először fejezze be "
        "vagy szakítsa meg őket. Semmi sem lett törölve."
    ),
    "project_delete.error.not_confirmed": (
        "A beírt szöveg nem egyezik a projektkulccsal. Semmi sem lett törölve."
    ),
    "project_delete.import_batches": "Importkötegek",
    "project_delete.items": "Elemek",
    "project_delete.link": "Projekt törlése",
    "project_delete.title": "Projekt törlése",
    "project_delete.warning": (
        "Ez véglegesen törli a(z) „{name}” projektet és minden tartalmát. "
        "A műveletet az irányítópultról nem lehet visszavonni."
    ),
    "project_delete.will_remove": "Ez törölni fogja",
    "project_delete.work_sessions": "Munkamenetek",
    "project_form.description": "Leírás",
    "project_form.description_placeholder": "Rövid leírás ehhez a munkaterülethez",
    "project_form.error.exists": "A(z) „{project_key}” projekt már létezik.",
    "project_form.error.exists_on_disk": "{name} már létezik a lemezen.",
    "project_form.error.invalid_key": (
        "A projektkulcs betűvel kezdődjön, és csak kisbetűket, számokat, - vagy _ "
        "karaktert tartalmazzon."
    ),
    "project_form.error.invalid_template": "Válasszon egy elérhető projektsablont.",
    "project_form.error.name_required": "A projekt neve kötelező.",
    "project_form.example_install": "Telepítés",
    "project_form.example_installed": "A(z) „{example_key}” sablonpélda telepítve.",
    "project_form.example_use": "Használat",
    "project_form.examples_help": "Telepítsen egy helyi példát, majd válassza ki lent.",
    "project_form.examples_title": "Példa sabloncsomagok",
    "project_form.help": (
        "Projektkonfiguráció létrehozása kezdősablonból. Később a TOML-fájlban módosíthatja "
        "a típusokat, állapotokat, ágakat és kiadási szabályokat."
    ),
    "project_form.key": "Projektkulcs",
    "project_form.key_help": "Kisbetűs URL/konfigurációs azonosító. Példa: acme-web.",
    "project_form.name": "Projekt neve",
    "project_form.name_placeholder": "Acme Web",
    "project_form.template_branches": "Ágak",
    "project_form.template_custom_fields": "Egyéni mezők",
    "project_form.template_kinds": "Típusok",
    "project_form.template_statuses": "Állapotok",
    "project_form.template_title": "Projektsablon",
    "project_template.agent.description": (
        "Emberi és ügynöki áttekintésre tervezve, blokkolt és kiadásra kész sorokkal."
    ),
    "project_template.agent.name": "Ügynöki munkafolyamat",
    "project_template.basic.description": (
        "Kisméretű alapértelmezett lista könnyű feladatkövetéshez és demókhoz."
    ),
    "project_template.basic.name": "Alap hibalista",
    "project_template.software.description": (
        "Szélesebb szoftverfejlesztési tábla epic-, felülvizsgálati és kiadási ágsávokkal."
    ),
    "project_template.software.name": "Szoftvercsapat",
    "relationship.add": "Kapcsolat hozzáadása",
    "relationship.empty": "Nincsenek kapcsolatok",
    "relationship.kind": "Kapcsolat típusa",
    "relationship.remove": "Kapcsolat eltávolítása",
    "relationship.target": "Célelem azonosítója",
    "relationship.target_placeholder": "Példa: PROJ-42",
    "relationship.title": "Kapcsolatok",
    "relationship.blocks": "Blokkolja",
    "relationship.blocked_by": "Blokkolta",
    "relationship.related_to": "Kapcsolódó",
    "live.apply": "Módosítások alkalmazása",
    "live.connected": "Élő",
    "live.connecting": "Kapcsolódás...",
    "live.notice": "Ez a nézet megváltozott.",
    "live.offline": "Nincs kapcsolat: időszakos frissítés",
    "settings.live.enabled": "A változások élő követése",
    "settings.live.event_activity": "Tevékenységi bejegyzések",
    "settings.live.event_items": "Elemek változásai",
    "settings.live.event_sessions": "Munkamenetek",
    "settings.live.events": "Követett események",
    "settings.live.editing_after_save": "Alkalmazás mentés után",
    "settings.live.editing_notice": "Értesítés megjelenítése",
    "settings.live.fallback": "Tartalék frissítési időköz (másodperc, 5–300)",
    "settings.live.help": (
        "A megnyitott nézetek újratöltés nélkül követik az ügynökök, az API vagy az "
        "importok változtatásait."
    ),
    "settings.live.highlight": (
        "A megváltozott bejegyzések kiemelése (másodperc, 0–30; 0 = ki)"
    ),
    "settings.live.indicator": "A kapcsolat jelzőjének megjelenítése",
    "settings.live.title": "Élő frissítés",
    "settings.live.view_item": "Elemoldal",
    "settings.live.view_kanban": "Kanban tábla",
    "settings.live.view_list": "Lista",
    "settings.live.view_overview": "Áttekintés",
    "settings.live.views": "Az élő frissítést követő nézetek",
    "settings.live.while_editing": "Ha a szerkesztett nézet megváltozik",
    "settings.reset_group": "E beállítások visszaállítása az alapértelmezettre",
    "settings.reset_group_confirm": "Visszaállítja ezt a beállításcsoportot az alapértelmezettre?",
    "settings.widget.completed_minutes": (
        "Az elmúlt percekben befejezett munkamenetek is (perc, 0–240; 0 = ki)"
    ),
    "settings.widget.help": (
        "Az Aktív ügynöki munkamenetek modul megjeleníthető az Áttekintés oldalon és a "
        "Kanban tábla tetején."
    ),
    "settings.widget.info": "A munkamenetnél megjelenített adatok",
    "settings.widget.info_agent": "Ügynök neve",
    "settings.widget.info_goal": "Cél",
    "settings.widget.info_item": "Elem",
    "settings.widget.info_last_update": "Utolsó frissítés",
    "settings.widget.info_updates": "Frissítések száma",
    "settings.widget.initial_state": "Kezdeti állapot",
    "settings.widget.max_sessions": "A munkamenetek legnagyobb száma (1–20)",
    "settings.widget.scope": "Hatókör",
    "settings.widget.scope_all": "Minden projekt",
    "settings.widget.scope_project": "Jelenlegi projekt",
    "settings.widget.show_kanban": "Megjelenítés a Kanban táblán",
    "settings.widget.show_overview": "Megjelenítés az Áttekintés oldalon",
    "settings.widget.state_collapsed": "Összecsukva",
    "settings.widget.state_expanded": "Kinyitva",
    "settings.widget.statuses": "A megjelenített munkamenet-állapotok",
    "settings.widget.title": "Ügynöki munkamenetek modul",
    "settings.accent": "Kiemelő szín",
    "settings.appearance": "Témaszínek",
    "settings.appearance_help": (
        "A világos és a sötét módhoz használt kiemelő színek beállítása. "
        "Az alaphelyzet visszaállítja a beépített palettát."
    ),
    "settings.audit": "Legutóbbi módosítások",
    "settings.audit_empty": "Még nincs rögzített módosítás.",
    "settings.config_tokens": "A server.toml tokenjei",
    "settings.copied": "Másolva",
    "settings.copy": "Másolás",
    "settings.created_msg": (
        "A token létrejött. Másolja ki most az értékét; csak egyszer jelenik meg."
    ),
    "settings.hide": "Elrejtés",
    "settings.regenerated_msg": "Új érték generálva. A régi érték már nem működik.",
    "settings.saved": "Mentve.",
    "settings.config_not_editable": (
        "A server.toml helye nem ismert, ezért ezek a tokenek itt nem módosíthatók."
    ),
    "settings.config_tokens_help": (
        "Ezek a tokenek a server.toml fájlban vannak. A módosítások a fájlba íródnak, "
        "és azonnal érvényesek. Újragenerálás után frissítse a token minden kliensét, "
        "például a .mcp.json fájlt."
    ),
    "settings.env_managed": "Az ISSUEDECK_API_TOKEN környezeti változó adja meg.",
    "settings.masked_value": "A token értékének maszkolt előnézete",
    "settings.regenerate_config_confirm": (
        "Újragenerálja ezt a tokent? A régi érték azonnal érvényét veszti, és a server.toml "
        "újraíródik. A régi értéket használó klienseket, például a .mcp.json fájlt, "
        "frissíteni kell."
    ),
    "settings.reveal": "Érték megjelenítése",
    "settings.token_value_help": "A token jelenlegi értéke. Ne ossza meg.",
    "settings.token_value_title": "A token értéke",
    "settings.create_token": "Token létrehozása",
    "settings.dark_mode": "Sötét mód",
    "settings.default_estimated_time": "Alapértelmezett becsült idő az új elemekhez (óra)",
    "settings.default_language": "Alapértelmezett nyelv",
    "settings.default_theme": "Alapértelmezett téma",
    "settings.delete_confirm": "Törli ezt a tokent? A használó alkalmazások leállnak.",
    "settings.display": "Megjelenítés",
    "settings.help": "A módosítások azonnal érvényesek, a szerver újraindítása nélkül.",
    "settings.hours_help": (
        "Üresen hagyva nincs alapértelmezés. Akkor használjuk, ha becslés nélkül jön létre elem."
    ),
    "settings.light_mode": "Világos mód",
    "settings.new_token_help": (
        "Másolja ki most. Később nem jelenik meg újra; ha elveszíti, generáljon újat."
    ),
    "settings.new_token_title": "Új token",
    "settings.no_runtime_tokens": "Itt még nincs létrehozott token.",
    "settings.nav": "Beállítások",
    "settings.primary": "Elsődleges",
    "settings.project": "Projekt",
    "settings.project_description": "Leírás",
    "settings.project_name": "Projekt neve",
    "settings.project_select": "Projekt",
    "settings.regenerate": "Újragenerálás",
    "settings.regenerate_confirm": (
        "Újragenerálja ezt a tokent? A jelenlegi érték azonnal érvényét veszti."
    ),
    "settings.reset_colours": "Színek alaphelyzetbe állítása",
    "settings.reset_confirm": "Visszaállítja mindkét színsémát a beépített palettára?",
    "settings.runtime_tokens": "Az irányítópulton létrehozott tokenek",
    "settings.theme_dark": "Sötét",
    "settings.theme_light": "Világos",
    "settings.theme_system": "Rendszer",
    "settings.title": "Beállítások",
    "settings.token_name": "Név",
    "settings.token_scopes": "Hatókörök",
    "settings.tokens": "API-tokenek",
    "settings.tokens_help": (
        "Tokenek létrehozása, átnevezése, hatókörének módosítása vagy újragenerálása. "
        "Az újragenerálás érvényteleníti a régi értéket."
    ),
    "settings.tracking": "Időkövetési alapértelmezések",
    "settings.tracking_help": "Az ezután létrehozott elemekre vonatkozik.",
    "settings.display_help": (
        "Az a nyelv és téma, amelyet a rendszer akkor használ, ha a felhasználó nem választott."
    ),
    "snapshot.title": "Projekt importálása pillanatképből",
    "snapshot.help": (
        "Projekt helyreállítása vagy másolása a Pillanatkép exportálása paranccsal készült "
        "ZIP-fájlból. Írás előtt pontosan látja, mi változna."
    ),
    "snapshot.file": "Pillanatkép-fájl (.zip)",
    "snapshot.file_help": (
        "A Pillanatkép exportálása vagy a projekttörlés biztonsági mentése által írt ZIP-fájl."
    ),
    "snapshot.mode": "Mit tegyünk",
    "snapshot.mode_create": "Új projekt létrehozása",
    "snapshot.mode_create_help": (
        "Felépít egy projektet az elemeivel, kapcsolataival, munkameneteivel és "
        "importelőzményeivel. A kulcs nem lehet foglalt."
    ),
    "snapshot.mode_update": "Meglévő projekt frissítése",
    "snapshot.mode_update_help": (
        "Hozzáadja, ami a projektből hiányzik. A projektből semmi nem törlődik."
    ),
    "snapshot.new_key": "Új projekt kulcsa (létrehozás)",
    "snapshot.new_key_placeholder": "Üresen: a pillanatkép kulcsa",
    "snapshot.target": "Frissítendő projekt (frissítés)",
    "snapshot.target_default": "A pillanatképben szereplő kulcsú projekt",
    "snapshot.conflict": "Mindkét helyen meglévő elemek (frissítés)",
    "snapshot.conflict_keep": "A projekt változata marad (alapértelmezett)",
    "snapshot.conflict_newer": "A pillanatkép változata, ha újabb",
    "snapshot.conflict_overwrite": "Mindig a pillanatkép változata",
    "snapshot.conflict_help": (
        "A hiányzó tevékenységi bejegyzések, kapcsolatok, munkamenetek és importcsomagok mindig "
        "hozzáadódnak."
    ),
    "snapshot.preview": "Pillanatkép ellenőrzése",
    "snapshot.preview_title": "Előnézet: még semmi sem íródott",
    "snapshot.preview_help": (
        "A(z) {source} pillanatképe ezekkel a változásokkal kerülne a(z) {project} projektbe."
    ),
    "snapshot.apply": "Importálás most",
    "snapshot.applied_title": "A pillanatkép importálva",
    "snapshot.applied_help": "A(z) {project} projekt naprakész a pillanatképpel.",
    "snapshot.open_project": "A projekt megnyitása",
    "snapshot.another": "Újabb pillanatkép importálása",
    "snapshot.items_created": "Létrehozott elemek",
    "snapshot.items_updated": "Frissített elemek",
    "snapshot.items_unchanged": "Változatlanul hagyott elemek",
    "snapshot.events_added": "Hozzáadott tevékenységi bejegyzések",
    "snapshot.relationships_added": "Hozzáadott kapcsolatok",
    "snapshot.images_added": "Hozzáadott képek",
    "snapshot.item_images_added": "Hozzáadott képkapcsolatok",
    "snapshot.documents_added": "Hozzáadott dokumentumok",
    "snapshot.item_documents_added": "Hozzáadott dokumentumkapcsolatok",
    "snapshot.work_sessions_added": "Hozzáadott munkamenetek",
    "snapshot.import_batches_added": "Hozzáadott importcsomagok",
    "snapshot.error.options": "A beállítások érvénytelenek.",
    "snapshot.error.no_file": "Először válasszon pillanatkép-fájlt.",
    "snapshot.error.too_large": "A fájl nagyobb, mint 64 MB.",
    "snapshot.error.expired": "Az ellenőrzött pillanatkép már nem érhető el; ellenőrizze újra.",
    "snapshot.link.import": "Pillanatkép importálása",
    "snapshot.link.from_new": "Importálás pillanatképből",
    "settings.github.title": "GitHub-exportok",
    "settings.github.help": (
        "A projektek egyszerű szövegfájlokként exportálhatók egy GitHub-tárolóba, és onnan "
        "importálhatók. A tokent a kiszolgáló egy környezeti változójából olvassa, itt soha nem "
        "tárolja és nem mutatja meg."
    ),
    "settings.github.repository": "Tároló (tulajdonos/név vagy URL)",
    "settings.github.branch": "Ág",
    "settings.github.folder": "Mappa a tárolóban (üresen: legfelső szint)",
    "settings.github.token_env": "A token környezeti változójának neve",
    "settings.github.allow_public": (
        "Nyilvános tároló engedélyezése (az elemek bizalmas szöveget tartalmazhatnak)"
    ),
    "settings.github.author_name": "A commit szerzőjének neve",
    "settings.github.author_email": "A commit szerzőjének e-mail-címe",
    "settings.github.test": "Kapcsolat tesztelése",
    "settings.github.test_title": "Kapcsolatellenőrzés (semmi sem íródott)",
    "settings.github.open_page": "Projektek exportálása és importálása",
    "github.title": "GitHub: projektek exportálása és importálása",
    "github.help": (
        "Tartsa a projekteket egy GitHub-tárolóban: minden export egy commit egyszerű "
        "szövegfájlokkal, és a projekt a tárolóból visszaállítható."
    ),
    "github.link": "Exportálás GitHubra",
    "github.repository_title": "Tároló",
    "github.change_settings": "Beállítások módosítása",
    "github.token_set": "a változó be van állítva ezen a kiszolgálón",
    "github.token_missing": "a változó nincs beállítva ezen a kiszolgálón",
    "github.hint.token_title": "Hiányzik a GitHub-token",
    "github.hint.token_body": (
        "A(z) {variable} változó nincs beállítva ezen a kiszolgálón. Állítsa be egy olyan "
        "GitHub-tokenre, amely olvashatja és írhatja a tároló tartalmát, majd állítsa le és "
        "indítsa újra a kiszolgálót: a kiszolgáló a környezetét csak indításkor olvassa be."
    ),
    "github.hint.settings": "A tároló és a változó neve: Beállítások, GitHub-exportok",
    "github.export_no_project": (
        "Az exporthoz projekt kell. Hozzon létre egyet, vagy importáljon egyet az alábbi "
        "tárolóból."
    ),
    "github.import_no_project": (
        "Még nincs projekt, ezért az import új projektet hoz létre."
    ),
    "github.export_title": "Projekt exportálása",
    "github.export_help": (
        "A projekt fájljait a tároló saját mappájába írja egyetlen commitként. Előbb ellenőrizze, "
        "mely fájlok változnának; ilyenkor semmi sem íródik."
    ),
    "github.project": "Projekt",
    "github.check": "Mi változna?",
    "github.export": "Exportálás most",
    "github.up_to_date": "{project}: a tároló naprakész, nem történt export.",
    "github.exported": "{project}: exportálva ({items} elem).",
    "github.would_export": "{project}: {items} elem lenne exportálva (semmi sem íródott).",
    "github.commit": "Commit",
    "github.files_changed": "A változó fájlok:",
    "github.import_title": "Projekt importálása",
    "github.import_help": (
        "Töltse be a tárolóban található projekteket, válasszon egyet, és ellenőrizze, mielőtt "
        "bármi íródna."
    ),
    "github.revision": "Változat (ág, címke vagy commit; üresen: az ág)",
    "github.load": "Projektek betöltése a tárolóból",
    "github.source": "Projekt a tárolóban",
    "github.remote_detail": "{items} elem, exportálva: {when}",
    "github.no_projects": "A tárolóban nem található exportált projekt.",
    "github.error.options": "A beállítások érvénytelenek.",
    "github.status.working": "Dolgozunk a GitHubbal…",
    "github.status.done": "Kész: {seconds} mp",
    "github.status.failed": "Megállt {seconds} mp után",
    "github.status.lost": (
        "Megszakadt a kapcsolat az irányítópulttal. A művelet még futhat; "
        "töltse újra az oldalt az eredményhez."
    ),
    "github.step.connecting": "Kapcsolódás a GitHubhoz és a tároló ellenőrzése",
    "github.step.reading_repo": "A tároló fájlainak beolvasása",
    "github.step.building": "A(z) {project} projekt fájlainak összeállítása",
    "github.step.comparing": "{count} fájl összehasonlítása a tárolóval",
    "github.step.uploading": "{i}. fájl feltöltése ({n} közül): {file}",
    "github.step.committing": "Commit létrehozása",
    "github.step.publishing": "Az ág frissítése",
    "github.step.reading_manifests": "{i}. projekt beolvasása ({n} közül): {project}",
    "github.step.downloading": "{i}. fájl letöltése ({n} közül): {file}",
    "github.step.checking": "A tartalom ellenőrzése",
    "github.step.importing": "A projekt írása",
    "github.error.busy": "Ez a művelet már fut. Várja meg, amíg befejeződik.",
    "github.error.job_unknown": (
        "A kiszolgáló már nem ismeri ezt a műveletet; töltse újra az oldalt."
    ),
    "search.placeholder": "Elemek keresése...",
    "search.empty": "Kezdjen el gépelni a kereséshez...",
    "search.all": "Összes találat megtekintése",
    "search.input_placeholder": "Elemcímek és tartalom keresése...",
    "search.no_query": "Elemcímek és tartalom keresése",
    "search.no_results_prefix": "Nincs találat erre:",
    "search.no_results_suffix": "",
    "saved_filters.delete": "Mentett szűrő törlése",
    "saved_filters.delete_named": "{name} mentett szűrő törlése",
    "saved_filters.name_placeholder": "Szűrő neve",
    "saved_filters.save_current": "Jelenlegi mentése",
    "saved_filters.title": "Mentett szűrők",
    "ship.commits_help": "Több SHA-t vesszővel válasszon el",
    "ship.commits_placeholder": "Adja meg a commit SHA-kat, vesszővel elválasztva",
    "ship.confirm": "Elem kiadása",
    "ship.modal_title": "Elem kiadása",
    "ship.records": "Kiadási rekordok",
    "ship.shipped_at": "Kiadás ideje",
    "ship.target_branch": "Céljágat",
    "stats.done": "Kész",
    "stats.estimated_time": "Becsült idő (óra)",
    "stats.in_progress": "Folyamatban",
    "stats.proposed": "Javasolt",
    "stats.time_spent": "Ráfordított idő (óra)",
    "stats.total": "Összes",
    "theme.toggle": "Téma váltása",
    "time.day_ago": "napja",
    "time.hour_ago": "órája",
    "time.just_now": "az imént",
    "time.minute_ago": "perce",
    "toast.network_error": "Hálózati hiba. Ellenőrizze a kapcsolatot.",
    "toast.request_failed": "A kérés sikertelen. Próbálja újra később.",
    "toast.status_updated": "Állapot frissítve",
    "toast.status_update_failed": "Az állapot frissítése sikertelen. Próbálja újra.",
    "queue.recent": "Nemrég érintett",
    "queue.backlog": "Backlog",
    "queue.active": "Aktív",
    "queue.blocked": "Blokkolva",
    "queue.ready_to_ship": "Kiadásra kész",
    "queue.done": "Kész",
    "queue.deleted": "Törölve",
    "work_session.empty": "Még nincsenek ügynöki munkamenetek",
    "work_session.goal": "Cél",
    "work_session.history": "Munkamenet-előzmények",
    "work_session.last_update": "Utolsó frissítés",
    "work_session.started": "Kezdés",
    "work_session.status.active": "Aktív",
    "work_session.status.canceled": "Megszakítva",
    "work_session.status.completed": "Befejezve",
    "work_session.status.paused": "Szüneteltetve",
    "work_session.title": "Ügynöki munkamenetek",
    "work_session.updates_suffix": "frissítés",
}

#: Hungarian names of the standard status keys (IS-0002). Custom status keys are
#: not listed here and keep the label from their project configuration.
STATUS_LABELS_HU: dict[str, str] = {
    "proposed": "Javasolt",
    "in_progress": "Folyamatban",
    "blocked": "Blokkolva",
    "ready_to_ship": "Kiadásra kész",
    "done": "Kész",
    "wontfix": "Nem javítandó",
}
