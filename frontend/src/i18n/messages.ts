import type { components } from "@/api/schema";

type Schemas = components["schemas"];
export type SprayRule = Schemas["SprayRuleOut"];

export type Locale = "es" | "en";
export const LOCALES: Locale[] = ["es", "en"];

const en = {
  intl: "en-GB",
  app: {
    apiDown: "Cannot reach the Field Watch API.",
    exploreTitle: "Fires in Entre Ríos and the Delta",
    exploreBody:
      "The map shows satellite fire detections as they arrive. Add your first field to see how far fires are and when it is good to spray.",
  },
  age: {
    unknown: "unknown",
    justNow: "just now",
    minutes: (n: number) => `${n} min ago`,
    hours: (n: number) => `${n} h ago`,
    days: (n: number) => `${n} d ago`,
  },
  units: { inside: "inside", ha: "ha" },
  directions: {
    N: "N",
    NE: "NE",
    E: "E",
    SE: "SE",
    S: "S",
    SW: "SW",
    W: "W",
    NW: "NW",
  } as Record<string, string>,
  confidence: { low: "low", nominal: "nominal", high: "high" } as Record<
    string,
    string
  >,
  severity: {
    CRITICAL: "Inside",
    VERY_HIGH: "Very close",
    HIGH: "Close",
    WATCH: "Nearby",
  },
  spray: {
    FAVORABLE: "Good to spray",
    CAUTION: "Caution",
    UNFAVORABLE: "Do not spray",
  },
  sprayShort: { FAVORABLE: "Good", CAUTION: "Caution", UNFAVORABLE: "No" },
  fire: {
    noDetections: "No fires",
    noData: "No fire data",
    stale: "Fire data old",
    possibleFire: (distance: string, direction: string) =>
      `Possible fire ${distance}${direction ? ` ${direction}` : ""}`,
    noneWithin: "No fire detected within 10 km",
    notReadYet: "Satellite data has not been read yet",
    lastRead: (age: string) => `Satellites last read ${age}`,
    more: (n: number) => `+${n} more`,
    seenBy: (sensors: string) => `Seen by ${sensors}`,
    confidence: (level: string) => `${level} confidence`,
    times: (pass: string, received: string) =>
      `Satellite pass ${pass} · received ${received}`,
    rulesVersion: (v: string) => `Rules version ${v}`,
    popupTitle: "Possible fire",
    detected: (age: string) => `detected ${age}`,
  },
  sprayText: {
    noForecast: "No forecast yet",
    stale: "Forecast old",
    allPass: "All conditions are good",
    nextWindow: (when: string) => `Next good window ${when}`,
    noWindow: "No good window in the next 48 h",
    now: "Now",
    driftToward: (side: string) => `Spray drift goes toward the ${side} side`,
    disclaimer:
      "Decision support with the default profile. Check the product label and your equipment.",
    everyRulePasses: "Every condition passes.",
    estimate: "estimate",
    timelineLabel: "Spraying conditions by hour",
  },
  rules: {
    wind: "Wind",
    gusts: "Gusts",
    delta_t: "Delta T",
    temperature: "Temperature",
    rain: "Rain",
    inversion: "Inversion",
    missing: (name: string) => `${name}: no data`,
    over: (name: string, value: string, limit: string) =>
      `${name} ${value}, over ${limit}`,
    near: (name: string, value: string, limit: string) =>
      `${name} ${value}, close to the limit ${limit}`,
    calm: (value: string) => `Wind only ${value}: drift can hang in still air`,
    lowDeltaT: (value: string) => `Delta T ${value}: droplets stay in the air`,
    highDeltaT: (value: string) => `Delta T ${value}: droplets evaporate`,
    rainAmount: (mm: string, h: number) => `${mm} of rain in the next ${h} h`,
    rainChance: (pct: string, h: number) =>
      `${pct} chance of rain in the next ${h} h`,
    inversionRisk:
      "Possible temperature inversion (estimated: calm, clear night or early morning)",
  },
  lightning: {
    label: "Lightning",
    none: "No lightning",
    count: (n: number) =>
      n === 1 ? "1 lightning flash" : `${n} lightning flashes`,
    sentence: (n: number, distance: string, minutes: number) =>
      `${n === 1 ? "1 flash" : `${n} flashes`} within 10 km in the last ${minutes} min, the nearest ${distance} away`,
    noneSentence: (minutes: number) =>
      `No lightning within 10 km in the last ${minutes} min`,
    noData: "No lightning data",
    last: (age: string) => `Last one ${age}`,
    why: "Lightning is the main natural cause of fires: watch the field for smoke in the next hours.",
  },
  history: {
    summary: (years: number, days: number, km: number) =>
      `In ${years} years, fire within ${km} km on ${days} ${days === 1 ? "day" : "days"}`,
    none: (years: number, km: number) =>
      `No fire within ${km} km in ${years} years`,
    months: (names: string[]) => `Most in ${names.join(" and ")}`,
    nearest: (distance: string, day: string) =>
      `The closest ${distance} away, ${day}`,
    latest: (day: string) => `The most recent on ${day}`,
    inside: (days: number) =>
      `Burned inside the field on ${days} ${days === 1 ? "day" : "days"}`,
    neverInside: "Never inside the field",
    perYear: "Fire days per year",
    perMonth: "By month",
    noData: "Fire history has not been loaded yet.",
    source:
      "NASA FIRMS archive, VIIRS S-NPP. A fire day is a day with at least one detection.",
  },
  forecast: {
    title: "Fire risk, next 3 days",
    days: ["Tomorrow", "Day after", "In 3 days"],
    band: {
      LOW: "Low",
      MODERATE: "Moderate",
      HIGH: "High",
      VERY_HIGH: "Very high",
    } as Record<string, string>,
    chip: (band: string) => `${band} fire risk tomorrow`,
    sentence: (pct: string) =>
      `${pct} chance that satellites see a fire within 10 km tomorrow`,
    why: "Why",
    nothingUnusual:
      "Nothing unusual today: dry, burning season and recent fires all within normal.",
    noData: "No forecast yet.",
    stale: "Forecast without today's weather; it uses the last day available.",
    note: "Predicts what satellites will detect near the field, not where a fire will start. Updated every hour.",
    factors: {
      fire_around_7d: (v: number) =>
        `Fires around in the last week (${v} ${v === 1 ? "day" : "days"})`,
      recent_cell_fire: (v: number) =>
        `Something burned in this area ${v} days ago`,
      dry_air: (v: number) => `Very dry air (${v} % humidity)`,
      no_rain: (v: number) => `${v} days without rain`,
      hot: (v: number) => `Hot (${v} °C)`,
      high_fwi: (v: number) => `High fire weather index (FWI ${v})`,
      burning_month: () => "This month usually burns here",
    } as Record<string, (v: number) => string>,
    layer: "Fire risk",
  },
  parcels: {
    layer: "Property lines",
  },
  sections: {
    fire: "Fire",
    history: "Fire history",
    lightning: "Lightning",
    spray: "Spraying, next 48 h",
    unusual: "Something unusual",
    unusualSoon:
      "Vegetation, water and burn scar changes from Sentinel-2 images are not available yet.",
  },
  detail: {
    field: "Field",
    lotOf: (field: string) => `Lot of ${field}`,
    close: "Close",
    editOutline: "Edit outline",
    deleteField: "Delete field",
    deleteLot: "Delete lot",
    confirmDelete: (name: string, withLots: boolean) =>
      `Delete ${name}${withLots ? " and its lots" : ""}?`,
  },
  portfolio: {
    allQuiet: (fields: number) => `No fires near your ${fields} fields`,
    withFire: (n: number) =>
      n === 1 ? "1 field has a fire nearby" : `${n} fields have a fire nearby`,
    sprayNow: (good: number, total: number) =>
      `Good to spray now: ${good} of ${total}`,
    counts: (fields: number, lots: number) => `${fields} fields · ${lots} lots`,
    select: (name: string) => `Select ${name}`,
    selected: (n: number) => `${n} selected`,
    showingSelected: (n: number) => `Showing ${n} selected`,
    showOnly: "Show only these",
    showAll: "Show all",
    clear: "Clear",
    hidden: (n: number) => `Hidden (${n})`,
    highPriority: "High priority",
    alertsOff: "Alerts off",
  },
  tags: {
    title: "Tags",
    add: "Add",
    addPlaceholder: "casa, cliente 1, crop:soy",
    remove: (label: string) => `Remove ${label}`,
    changeColor: (label: string) => `Color of ${label}`,
  },
  colorBy: { label: "Color fields by", status: "Status", tags: "Tags" },
  signIn: {
    button: "Sign in",
    title: "Sign in to Field Watch",
    why: "We email you a link, no password. Your fields stay in your account and alerts go to that address.",
    email: "Email",
    send: "Email me the link",
    sending: "Sending…",
    sent: (email: string) => `Check ${email}: the link expires in 15 minutes.`,
    expired: "That link was already used or expired. Ask for a new one.",
    failed: "The email could not be sent. Try again in a minute.",
    close: "Close",
    account: (email: string) => `Signed in as ${email}`,
    signOut: "Sign out",
    signedOutBody:
      "Sign in with your email to mark your fields, see how far fires are from them and get alerts by email.",
  },
  weather: {
    title: "Weather",
    noData: "No weather for this field yet.",
    wind: (from: string, kmh: string) => `wind from ${from} ${kmh} km/h`,
    gusts: (kmh: string) => `gusts ${kmh}`,
    rain24h: (mm: string) => `${mm} mm in 24 h`,
    humidity: (pct: string) => `humidity ${pct} %`,
    clouds: (pct: string) => `clouds ${pct} %`,
    rainChance: (pct: string) => `up to ${pct} % chance of rain`,
    noRain: "no rain in the next 24 h",
    from: (age: string) => `forecast from ${age}`,
    next48: "Next 48 h",
    stripLegend: "Temperature, wind/gusts in km/h, rain.",
  },
  settings: {
    title: "Settings",
    alerts: "Alert me of danger nearby",
    alertsHint: (email: string) => `By email to ${email}, and in this browser.`,
    allowBrowser: "Allow alerts in this browser",
    browserBlocked:
      "This browser blocks alerts from Field Watch; allow them in its site settings.",
    visible: "Show on the map",
    priority: "Priority",
    priorities: { HIGH: "High", NORMAL: "Normal", LOW: "Low" },
  },
  search: { placeholder: "Search fields, lots or tags", lot: "lot" },
  freshness: {
    apiDown: "API unreachable",
    noData: "No satellite data yet",
    lastPass: (sensor: string, age: string) => `Last pass ${sensor} · ${age}`,
    checked: (age: string) => `checked ${age}`,
    stale: (age: string) => `Satellite data old · checked ${age}`,
    partial: "some sensors failed",
  },
  buttons: {
    layers: "Map layers",
    locate: "Go to my location",
    addField: "Add field",
    goToFields: "Go to my fields",
    addFieldLabel: "Draw a new field",
    language: "Language",
  },
  basemaps: { dark: "Dark", light: "Light", satellite: "Satellite" },
  sheet: { resize: "Resize panel" },
  draw: {
    cancel: "Cancel",
    newField: "New field",
    newLot: (field: string) => `New lot in ${field}`,
    startOver: "Start over",
    tools: "Drawing tool",
    trace: "Trace",
    corners: "Corners",
    parcel: "Parcel",
    detect: "Detect",
    hints: {
      parcel:
        "Tap the field on the map: its official parcel outline from the provincial cadastre is used.",
      detect:
        "Tap inside the field: its outline is found in a year of satellite images.",
      trace:
        "Press on the edge of the field and drag your finger all around it. Lift to close.",
      corners: "Tap each corner. Tap the first corner again to close.",
    },
    zoomHint: "Zoom with two fingers or the wheel.",
    searching: "Looking up the parcel…",
    detecting: "Detecting the field in satellite images…",
    detected: (dates: number, first: string, last: string) =>
      `Detected in Sentinel-2 images (${dates} dates, ${first} to ${last}). Check the outline.`,
    notices: {
      too_small: "That shape is too small. Go around the whole field.",
      no_parcel: "No cadastral parcel there. Try Detect, Trace or Corners.",
      no_field_found:
        "No clear field boundary around that point. Try Trace or Corners.",
      no_images: "No clear satellite images there in the last year.",
      detect_failed: "The images could not be read. Try again in a minute.",
    },
    fromParcel: (partida: number, plano: number | null) =>
      `Parcel ${partida}${plano ? `, plan ${plano}` : ""}.`,
    fitting: "Fitting it to the property lines…",
    fitted: {
      parcels: (n: number) =>
        n === 1 ? "Fitted to 1 parcel." : `Fitted to ${n} parcels.`,
      edges: () => "Edges moved onto the nearby property lines.",
    } as Record<"parcels" | "edges", (parcels: number) => string>,
    yourDrawing: "Your drawing, as you made it.",
    useMine: "Use my drawing",
    fitAgain: "Fit to property lines",
    adjust: "Drag the points on the map to fit the edge exactly.",
    namePlaceholder: "Name, e.g. La Esperanza",
    name: "Name",
    save: "Save",
    saving: "Saving…",
    more: "Make it a lot or add tags",
    lotOf: "Lot of an existing field",
    ownField: "No, it is a field of its own",
    tags: "Tags, separated by commas",
    saveFailed: (detail: string) => `Could not save: ${detail}`,
    errors: {
      outside_country: "Fields can only be drawn inside Argentina.",
      outside_parent: "The lot must be inside its field.",
      invalid_polygon:
        "The outline crosses itself. Start over and go around once.",
      no_overlap: "That piece does not touch the field.",
      nothing_left: "That would remove the whole field.",
      no_change: "That piece is already part of the field.",
      cuts_lots: "That would leave part of a lot outside the field.",
    } as Record<string, string>,
  },
  edit: {
    title: (name: string) => `Edit ${name}`,
    pencils: "Add or remove",
    add: "Add",
    remove: "Remove",
    hints: {
      add: "Draw the piece to add.",
      remove: "Draw the piece to cut out.",
    } as Record<"add" | "remove", string>,
    checking: "Checking the new outline…",
    result: (name: string, hectares: string) =>
      `${name} will have ${hectares}.`,
    save: {
      add: "Add to the field",
      remove: "Remove from the field",
    } as Record<"add" | "remove", string>,
  },
};

export type Messages = typeof en;

const es: Messages = {
  intl: "es-AR",
  app: {
    apiDown: "No se puede conectar con la API de Field Watch.",
    exploreTitle: "Fuegos en Entre Ríos y el Delta",
    exploreBody:
      "El mapa muestra los focos detectados por satélite a medida que llegan. Agregá tu primer campo para ver a qué distancia están y cuándo conviene pulverizar.",
  },
  age: {
    unknown: "sin dato",
    justNow: "recién",
    minutes: (n) => `hace ${n} min`,
    hours: (n) => `hace ${n} h`,
    days: (n) => `hace ${n} d`,
  },
  units: { inside: "adentro", ha: "ha" },
  directions: {
    N: "N",
    NE: "NE",
    E: "E",
    SE: "SE",
    S: "S",
    SW: "SO",
    W: "O",
    NW: "NO",
  },
  confidence: { low: "baja", nominal: "media", high: "alta" },
  severity: {
    CRITICAL: "Adentro",
    VERY_HIGH: "Muy cerca",
    HIGH: "Cerca",
    WATCH: "En la zona",
  },
  spray: {
    FAVORABLE: "Se puede pulverizar",
    CAUTION: "Precaución",
    UNFAVORABLE: "No pulverizar",
  },
  sprayShort: { FAVORABLE: "Sí", CAUTION: "Precaución", UNFAVORABLE: "No" },
  fire: {
    noDetections: "Sin fuegos",
    noData: "Sin datos de fuego",
    stale: "Datos viejos",
    possibleFire: (distance, direction) =>
      `Posible fuego a ${distance}${direction ? ` al ${direction}` : ""}`,
    noneWithin: "Ningún fuego detectado a menos de 10 km",
    notReadYet: "Todavía no se leyeron los satélites",
    lastRead: (age) => `Satélites leídos ${age}`,
    more: (n) => `+${n} más`,
    seenBy: (sensors) => `Lo vio ${sensors}`,
    confidence: (level) => `confianza ${level}`,
    times: (pass, received) =>
      `Pasada del satélite ${pass} · recibido ${received}`,
    rulesVersion: (v) => `Versión de reglas ${v}`,
    popupTitle: "Posible fuego",
    detected: (age) => `detectado ${age}`,
  },
  sprayText: {
    noForecast: "Todavía no hay pronóstico",
    stale: "Pronóstico viejo",
    allPass: "Todas las condiciones están bien",
    nextWindow: (when) => `Próxima ventana buena ${when}`,
    noWindow: "No hay ventana buena en las próximas 48 h",
    now: "Ahora",
    driftToward: (side) => `La deriva va hacia el lado ${side}`,
    disclaimer:
      "Ayuda para decidir con el perfil por defecto. Revisá la etiqueta del producto y tu equipo.",
    everyRulePasses: "Todas las condiciones se cumplen.",
    estimate: "estimado",
    timelineLabel: "Condiciones para pulverizar por hora",
  },
  rules: {
    wind: "Viento",
    gusts: "Ráfagas",
    delta_t: "Delta T",
    temperature: "Temperatura",
    rain: "Lluvia",
    inversion: "Inversión",
    missing: (name) => `${name}: sin dato`,
    over: (name, value, limit) => `${name} ${value}, más que ${limit}`,
    near: (name, value, limit) => `${name} ${value}, cerca del límite ${limit}`,
    calm: (value) => `Viento de solo ${value}: la deriva queda suspendida`,
    lowDeltaT: (value) => `Delta T ${value}: las gotas quedan en el aire`,
    highDeltaT: (value) => `Delta T ${value}: las gotas se evaporan`,
    rainAmount: (mm, h) => `${mm} de lluvia en las próximas ${h} h`,
    rainChance: (pct, h) =>
      `${pct} de probabilidad de lluvia en las próximas ${h} h`,
    inversionRisk:
      "Posible inversión térmica (estimada: calma y cielo despejado, de noche o temprano)",
  },
  lightning: {
    label: "Rayos",
    none: "Sin rayos",
    count: (n) => (n === 1 ? "1 rayo" : `${n} rayos`),
    sentence: (n, distance, minutes) =>
      `${n === 1 ? "1 rayo" : `${n} rayos`} a menos de 10 km en los últimos ${minutes} min, el más cercano a ${distance}`,
    noneSentence: (minutes) =>
      `Sin rayos a menos de 10 km en los últimos ${minutes} min`,
    noData: "Sin datos de rayos",
    last: (age) => `El último ${age}`,
    why: "Los rayos son la principal causa natural de incendios: mirá si aparece humo en las próximas horas.",
  },
  history: {
    summary: (years, days, km) =>
      `En ${years} años, fuego a menos de ${km} km en ${days} ${days === 1 ? "día" : "días"}`,
    none: (years, km) => `Sin fuego a menos de ${km} km en ${years} años`,
    months: (names) => `Sobre todo en ${names.join(" y ")}`,
    nearest: (distance, day) => `El más cercano a ${distance}, el ${day}`,
    latest: (day) => `El más reciente el ${day}`,
    inside: (days) =>
      `Se quemó dentro del campo ${days} ${days === 1 ? "día" : "días"}`,
    neverInside: "Nunca dentro del campo",
    perYear: "Días con fuego por año",
    perMonth: "Por mes",
    noData: "Todavía no se cargó el historial de fuegos.",
    source:
      "Archivo de NASA FIRMS, VIIRS S-NPP. Un día con fuego es un día con al menos una detección.",
  },
  forecast: {
    title: "Riesgo de fuego, próximos 3 días",
    days: ["Mañana", "Pasado", "En 3 días"],
    band: {
      LOW: "Bajo",
      MODERATE: "Moderado",
      HIGH: "Alto",
      VERY_HIGH: "Muy alto",
    },
    chip: (band) => `Riesgo ${band.toLowerCase()} mañana`,
    sentence: (pct) =>
      `${pct} de probabilidad de que el satélite vea fuego a menos de 10 km mañana`,
    why: "Por qué",
    nothingUnusual:
      "Nada fuera de lo normal hoy: sequedad, época de quemas y fuegos recientes dentro de lo habitual.",
    noData: "Todavía no hay pronóstico.",
    stale: "Pronóstico sin el clima de hoy; usa el último día disponible.",
    note: "Predice lo que el satélite va a detectar cerca del campo, no dónde se va a prender un fuego. Se actualiza cada hora.",
    factors: {
      fire_around_7d: (v) =>
        `Hubo fuego alrededor esta semana (${v} ${v === 1 ? "día" : "días"})`,
      recent_cell_fire: (v) => `Se quemó algo en esta zona hace ${v} días`,
      dry_air: (v) => `Aire muy seco (${v} % de humedad)`,
      no_rain: (v) => `${v} días sin llover`,
      hot: (v) => `Calor (${v} °C)`,
      high_fwi: (v) => `Índice de peligro de incendio alto (FWI ${v})`,
      burning_month: () => "En este mes suele haber quemas acá",
    },
    layer: "Riesgo de fuego",
  },
  parcels: {
    layer: "Líneas de propiedad",
  },
  sections: {
    fire: "Fuego",
    history: "Historial de fuegos",
    lightning: "Rayos",
    spray: "Pulverización, próximas 48 h",
    unusual: "Algo raro en el campo",
    unusualSoon:
      "Los cambios de vegetación, agua y áreas quemadas con imágenes Sentinel-2 todavía no están disponibles.",
  },
  detail: {
    field: "Campo",
    lotOf: (field) => `Lote de ${field}`,
    close: "Cerrar",
    editOutline: "Editar borde",
    deleteField: "Borrar campo",
    deleteLot: "Borrar lote",
    confirmDelete: (name, withLots) =>
      `¿Borrar ${name}${withLots ? " y sus lotes" : ""}?`,
  },
  portfolio: {
    allQuiet: (fields) => `Sin fuegos cerca de tus ${fields} campos`,
    withFire: (n) =>
      n === 1 ? "1 campo tiene fuego cerca" : `${n} campos tienen fuego cerca`,
    sprayNow: (good, total) => `Para pulverizar ahora: ${good} de ${total}`,
    counts: (fields, lots) => `${fields} campos · ${lots} lotes`,
    select: (name) => `Seleccionar ${name}`,
    selected: (n) => (n === 1 ? "1 seleccionado" : `${n} seleccionados`),
    showingSelected: (n) =>
      n === 1 ? "Mostrando 1 seleccionado" : `Mostrando ${n} seleccionados`,
    showOnly: "Ver solo estos",
    showAll: "Ver todos",
    clear: "Limpiar",
    hidden: (n) => `Ocultos (${n})`,
    highPriority: "Prioridad alta",
    alertsOff: "Sin avisos",
  },
  tags: {
    title: "Etiquetas",
    add: "Agregar",
    addPlaceholder: "casa, cliente 1, crop:soy",
    remove: (label) => `Quitar ${label}`,
    changeColor: (label) => `Color de ${label}`,
  },
  colorBy: {
    label: "Colorear campos por",
    status: "Estado",
    tags: "Etiquetas",
  },
  signIn: {
    button: "Entrar",
    title: "Entrá a Field Watch",
    why: "Te mandamos un link por mail, sin contraseña. Tus campos quedan en tu cuenta y los avisos llegan a esa dirección.",
    email: "Mail",
    send: "Mandame el link",
    sending: "Mandando…",
    sent: (email) => `Revisá ${email}: el link vence en 15 minutos.`,
    expired: "Ese link ya se usó o venció. Pedí otro.",
    failed: "No se pudo mandar el mail. Probá de nuevo en un minuto.",
    close: "Cerrar",
    account: (email) => `Entraste como ${email}`,
    signOut: "Salir",
    signedOutBody:
      "Entrá con tu mail para marcar tus campos, ver a qué distancia están los fuegos y recibir avisos por mail.",
  },
  weather: {
    title: "Clima",
    noData: "Todavía no hay clima para este campo.",
    wind: (from, kmh) => `viento del ${from} ${kmh} km/h`,
    gusts: (kmh) => `ráfagas ${kmh}`,
    rain24h: (mm) => `${mm} mm en 24 h`,
    humidity: (pct) => `humedad ${pct} %`,
    clouds: (pct) => `nubes ${pct} %`,
    rainChance: (pct) => `hasta ${pct} % de probabilidad de lluvia`,
    noRain: "sin lluvia en las próximas 24 h",
    from: (age) => `pronóstico de ${age}`,
    next48: "Próximas 48 h",
    stripLegend: "Temperatura, viento/ráfagas en km/h, lluvia.",
  },
  settings: {
    title: "Ajustes",
    alerts: "Avisarme si hay peligro cerca",
    alertsHint: (email) => `Por mail a ${email} y en este navegador.`,
    allowBrowser: "Permitir avisos en este navegador",
    browserBlocked:
      "Este navegador bloquea los avisos de Field Watch; permitilos en la configuración del sitio.",
    visible: "Mostrar en el mapa",
    priority: "Prioridad",
    priorities: { HIGH: "Alta", NORMAL: "Normal", LOW: "Baja" },
  },
  search: { placeholder: "Buscar campos, lotes o etiquetas", lot: "lote" },
  freshness: {
    apiDown: "Sin conexión con la API",
    noData: "Todavía no hay datos satelitales",
    lastPass: (sensor, age) => `Última pasada ${sensor} · ${age}`,
    checked: (age) => `revisado ${age}`,
    stale: (age) => `Datos satelitales viejos · revisado ${age}`,
    partial: "fallaron algunos sensores",
  },
  buttons: {
    layers: "Capas del mapa",
    locate: "Ir a mi ubicación",
    addField: "Agregar campo",
    goToFields: "Ir a mis campos",
    addFieldLabel: "Dibujar un campo nuevo",
    language: "Idioma",
  },
  basemaps: { dark: "Oscuro", light: "Claro", satellite: "Satélite" },
  sheet: { resize: "Cambiar el tamaño del panel" },
  draw: {
    cancel: "Cancelar",
    newField: "Campo nuevo",
    newLot: (field) => `Lote nuevo en ${field}`,
    startOver: "Empezar de nuevo",
    tools: "Herramienta de dibujo",
    trace: "Trazar",
    corners: "Esquinas",
    parcel: "Parcela",
    detect: "Detectar",
    hints: {
      parcel:
        "Tocá el campo en el mapa: se usa el borde oficial de la parcela del catastro provincial.",
      detect:
        "Tocá adentro del campo: su borde se encuentra en un año de imágenes satelitales.",
      trace:
        "Apoyá el dedo en el borde del campo y recorrelo entero. Levantá el dedo para cerrar.",
      corners: "Tocá cada esquina. Tocá la primera otra vez para cerrar.",
    },
    zoomHint: "Hacé zoom con dos dedos o la rueda.",
    searching: "Buscando la parcela…",
    detecting: "Detectando el campo en imágenes satelitales…",
    detected: (dates, first, last) =>
      `Detectado en imágenes Sentinel-2 (${dates} fechas, del ${first} al ${last}). Revisá el borde.`,
    notices: {
      too_small: "La forma es muy chica. Recorré todo el campo.",
      no_parcel:
        "No hay una parcela catastral ahí. Probá con Detectar, Trazar o Esquinas.",
      no_field_found:
        "No se ve un borde claro alrededor de ese punto. Probá con Trazar o Esquinas.",
      no_images: "No hay imágenes satelitales despejadas ahí en el último año.",
      detect_failed:
        "No se pudieron leer las imágenes. Probá de nuevo en un minuto.",
    },
    fromParcel: (partida, plano) =>
      `Partida ${partida}${plano ? `, plano ${plano}` : ""}.`,
    fitting: "Ajustando a las líneas de propiedad…",
    fitted: {
      parcels: (n) =>
        n === 1 ? "Ajustado a 1 parcela." : `Ajustado a ${n} parcelas.`,
      edges: () => "Bordes llevados a las líneas de propiedad cercanas.",
    },
    yourDrawing: "Tu dibujo, tal como lo hiciste.",
    useMine: "Volver a mi dibujo",
    fitAgain: "Ajustar a las líneas",
    adjust: "Arrastrá los puntos en el mapa para ajustar el borde.",
    namePlaceholder: "Nombre, por ejemplo La Esperanza",
    name: "Nombre",
    save: "Guardar",
    saving: "Guardando…",
    more: "Hacerlo lote o agregar etiquetas",
    lotOf: "Lote de un campo existente",
    ownField: "No, es un campo propio",
    tags: "Etiquetas, separadas por comas",
    saveFailed: (detail) => `No se pudo guardar: ${detail}`,
    errors: {
      outside_country: "Solo se pueden dibujar campos dentro de Argentina.",
      outside_parent: "El lote tiene que estar dentro de su campo.",
      invalid_polygon:
        "El borde se cruza a sí mismo. Empezá de nuevo y dá una sola vuelta.",
      no_overlap: "Ese pedazo no toca el campo.",
      nothing_left: "Así se borraría el campo entero.",
      no_change: "Ese pedazo ya es parte del campo.",
      cuts_lots: "Así quedaría parte de un lote fuera del campo.",
    },
  },
  edit: {
    title: (name) => `Editar ${name}`,
    pencils: "Agregar o quitar",
    add: "Agregar",
    remove: "Quitar",
    hints: {
      add: "Dibujá el pedazo a agregar.",
      remove: "Dibujá el pedazo a sacar.",
    },
    checking: "Revisando el borde nuevo…",
    result: (name, hectares) => `${name} va a quedar con ${hectares}.`,
    save: { add: "Agregar al campo", remove: "Quitar del campo" },
  },
};

export const MESSAGES: Record<Locale, Messages> = { en, es };
