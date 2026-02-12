# Pflichtfelder (temporär deaktiviert)

## Formular-Felder (Zeilen 577-625)

```html
<select id="process" required>
<input id="date" type="date" required>
<input id="time" type="time" required>
<input id="location" type="text" required>
<input id="employee" type="text" required>
<input id="plate" type="text" required>
<input id="model" type="text" required>
<input id="mileage" type="number" required>
```

## Pflichtfotos (Zeilen 758-765)

```javascript
{id:"p_front", title:"Foto 1 - Front", required:true},
{id:"p_rear", title:"Foto 2 - Heck", required:true},
{id:"p_left", title:"Foto 3 - Links", required:true},
{id:"p_right", title:"Foto 4 - Rechts", required:true},
{id:"p_dashboard", title:"Foto 5 - Cockpit/Display", required:true},
{id:"p_frontinside", title:"Foto 6 - Innen vorne", required:true},
{id:"p_rearinside", title:"Foto 7 - Innen hinten", required:true},
{id:"p_trunk", title:"Foto 8 - Kofferraum", required:true},
```

## Wiederherstellen

```bash
# Formular-Felder
sed -i 's/id="process">/id="process" required>/' index.html
sed -i 's/id="date" type="date">/id="date" type="date" required>/' index.html
# ... etc

# Fotos
sed -i 's/required:false/required:true/g' index.html
```

---
Erstellt: 2026-02-06
