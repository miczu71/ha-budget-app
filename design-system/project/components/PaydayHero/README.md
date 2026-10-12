Hero „Do wypłaty” (M21) i kafelek prognozy z tygodniami okresu (M21 E4) oraz rezerwacją do skarbonek (M10 E1).

`section.payday-hero` (na bazie `flex-hero`): limit dzienny w `hero-amount` z jednostką `span.hero-unit`, werdykt prognozy, pasek upływu okresu od wypłaty i linia `p.week-line` z paskiem bieżącego tygodnia (wydane z limitu, zostało). Tygodnie są kalendarzowe pon–nd, przycięte do okresu wypłaty.

`ul.rows.fc-weeks` w kafelku prognozy: wiersz = zakres dat i kwota, pod nimi pasek `flex-bar` na całą szerokość (`grid-column: 1 / -1`). Stan tygodnia w klasie `li`: `week-past` (miara: limit z początku okresu, `over` przy przekroczeniu), `week-now` (pogrubiona data; limit = wydane + dzisiejszy limit na resztę tygodnia), `week-next` (bez paska, „plan”).

`dl.fc-strip` ma piątą komórkę „Do skarbonek”, gdy jest nieprzelane odłożenie: na telefonie zajmuje cały wiersz, od 720 px pasek ma 5 kolumn. Zdarzenie „Do skarbonek” w `fc-list` prowadzi do ekranu Skarbonki; wydatek serii pokryty saldem skarbonki ma kwotę 0 i dopisek.

- Konsument dostarcza kwoty, procenty (`style="width: …%"`) i daty.
