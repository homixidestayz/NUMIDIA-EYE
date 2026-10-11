import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

/* English and Arabic for the text panels.
 *
 *  Two rules govern this file:
 *
 *  1. The map and the timeline stay left-to-right, as map applications
 *     conventionally do. `dir` is therefore applied to individual text panels,
 *     never to <html> — direction is inherited, so a global flip would drag
 *     the map and timeline with it. <html> carries `lang` only.
 *
 *  2. Strings the API returns are English by design and are NOT localised.
 *     Priority methodology, factor names and evidence, and the verifier's
 *     scope and message all come from a versioned English pipeline. They are
 *     rendered inside `lang="en" dir="ltr"` spans so a screen reader switches
 *     voice and the reader is never shown a string pretending to be localised.
 *     The same applies to legal attribution details. */
export type Lang = "en" | "ar";

export const dict = {
  en: {
    tagline: "Wildfire intelligence for Algeria",
    loading: "Loading…",
    /* "Unavailable" is a claim: the upstream was asked and declined. It must
       stay distinguishable from "loading" and from an actual zero. */
    unavailable: "Unavailable",
    jump: "Jump to a wilaya…",
    jumpPlaceholder: "Jump to a wilaya — try Blida, Timimoun or 9",
    searchLabel: "Search wilayas",
    openSearch: "Open wilaya search",
    layers: "Layers",
    detail: "Detail",
    liveOf: "live",
    langName: "العربية",
    langLabel: "Switch language to Arabic",
    layerWilayas: "Wilaya boundaries",
    layerDetections: "Fire detections",
    layerLabels: "Wilaya labels",
    incidents: "Incidents & priority",
    incidentsLede: "Rule-based priority over grouped FIRMS detections. Not confirmed wildfires.",
    grouping: "Grouping incidents… this takes a few seconds.",
    noIncidents:
      "No incidents grouped from the stored detections. The pipeline is up but nothing is stored yet — that is different from an absence of fires.",
    detections: "detections",
    priorityTitle: "rule-based priority score",
    closePanel: "Close detail panel",
    pickPrefix: "Pick a detection on the map, an incident from the list, or press",
    pickSuffix: "to jump to a wilaya.",
    groupingStatus: "Grouping status",
    priorityRule: "Priority — rule-based",
    verification: "Verification state",
    status: "Status",
    evaluated: "Evaluated",
    detection: "Detection",
    wilaya: "Wilaya",
    coordinates: "Coordinates",
    acquired: "Acquired",
    satellite: "Satellite",
    brightness: "Brightness Ti4",
    firmsConfidence: "FIRMS confidence",
    state: "State",
    verifying: "Verifying…",
    runAi: "Run AI verification",
    result: "Result",
    probability: "Probability",
    model: "Model",
    threshold: "Threshold",
    calibrated: "Calibrated",
    yes: "yes",
    no: "no",
    notCalibrated:
      "Not calibrated — this is a model score, not a literal probability of fire.",
    envTitle: "Environment at incident",
    envLoading: "Loading environmental context…",
    envUnavailable: "Environmental context unavailable.",
    wind: "Wind",
    gusts: "Gusts",
    temp: "Temp",
    humidity: "Humidity",
    soil01: "Soil 0–1",
    soil39: "Soil 3–9",
    soilTemp: "Soil temp",
    elevation: "Elevation",
    soilMoisture: "Soil moisture",
    noteHumidity: "Moist ← · → Drying",
    noteSoil: "Deep ← · → Shallow fuel",
    noteWind: "Calm ← · → Strong",
    bandsOnly: "Bands describe measured conditions only. No fire-risk score, no verdict.",
    refreshEnv: "Refresh environment",
    tlLabel: "Timeline",
    tlRange: "Time range",
    tlReplayTitle:
      "Replay recorded detections through time. This is playback of stored data, not a forecast.",
    tlStop: "❚❚ Stop",
    tlReplay: "▶ Replay",
    tlFoot:
      "Replay steps through recorded detections. Times are Algeria local (UTC+1). Not a fire-spread model and not a forecast.",
    mapWilayas: "Wilayas",
    mapFires: "Fires",
    mapLabels: "Labels",
    mapFailed: "failed",
    mapStarting: "starting map…",
    mapLoading: "loading",
    mapDrawn: "features drawn",
    /* Lowercase: this one sits mid-sentence in the provenance readout, so it
       must not borrow the capitalised legend label. */
    statWilayas: "wilayas",
    mapUnavailable: "Map unavailable.",
    clearFilter: "Clear the wilaya filter",
    filteredTo: "Filtered to",
    noneInView: "No detections in view",
    hasNone: "has none",
    noneWord: "None",
    inRange: "in the selected range.",
    loadedWiden: "are loaded — widen the range to see them.",
    frpTitle: "Fire Radiative Power",
    historicalObs: "Historical observation",
    indep: "Independent research prototype. Not affiliated with or endorsed by any government body. Not a fire-spread model.",
    footer:
      "Independent research prototype. Not affiliated with any government body. Not a fire-spread model. Data: NASA FIRMS/VIIRS · Open-Meteo · GeoAlgeria (ODbL).",
    apiDown: "Cannot reach the API.",
    apiDownHint: "— start it with",
    apiDownTail: "and reload.",
    tlOnMap: "on map",
    tlInRange: "in range",
    tlShown: "shown",
    tlLoaded: "loaded",
    moveStart: "Move window start",
    moveEnd: "Move window end",
    panWindow: "Pan the time window",
    tlOnlyPre: "Only",
    tlOnlyPost: "of detections are loaded, so this range would show the same points.",
    rngToday: "Today",
    rngTodayTitle: "00:00 Algeria time to now",
    rng24h: "24H",
    rng24hTitle: "Rolling 24 hours to now",
    rng7d: "7D",
    rng7dTitle: "Rolling 7 days to now",
    rngAll: "All",
    rngAllTitle: "Everything currently loaded",
    noDataset: "No dataset, contributes nothing:",
    envCentroid: "incident centroid",
    envObserved: "observed",
    priorityNote:
      "priority-v1 is deterministic and rule-based. It is not the AI verifier and never uses model output.",
    windCapPre: "The arrow points the way the wind blows",
    windTo: "to",
    windCapPost: ". Open-Meteo reports bearing from. Not a fire-spread model.",
    clusterSpread: "Cluster spread",
    searchNoMatchPre: "No wilaya matches",
    searchLoadedSuf: "wilayas loaded.",
    searchDet: "det.",
    searchNoDet: "no detections",
    tlBarOne: "detection",
    tlBarMany: "detections",
    tlAt: "at",
    attribLabel: "Data attribution",
    attrDetections: "Fire detections",
    attrBoundaries: "Wilaya boundaries",
    attrWorld: "World outlines",
    attrWeather: "Weather",
    attrRenderer: "Map renderer",
  },
  ar: {
    tagline: "استخبارات حرائق الغابات للجزائر",
    loading: "جارٍ التحميل…",
    unavailable: "غير متوفر",
    jump: "انتقل إلى ولاية…",
    jumpPlaceholder: "انتقل إلى ولاية — جرّب البليدة أو تيميمون أو 9",
    searchLabel: "ابحث في الولايات",
    openSearch: "فتح البحث عن الولايات",
    layers: "الطبقات",
    detail: "التفاصيل",
    liveOf: "مباشر",
    langName: "English",
    langLabel: "التبديل إلى الإنجليزية",
    layerWilayas: "حدود الولايات",
    layerDetections: "رصد الحرائق",
    layerLabels: "أسماء الولايات",
    incidents: "الحوادث والأولوية",
    incidentsLede: "أولوية قائمة على قواعد لرصد FIRMS المجمّع. ليست حرائق مؤكدة.",
    grouping: "جارٍ تجميع الحوادث… يستغرق ذلك بضع ثوانٍ.",
    noIncidents:
      "لا توجد حوادث مجمّعة من الرصد المخزَّن. المنظومة تعمل لكن لا شيء مخزَّن بعد — وهذا لا يعني غياب الحرائق.",
    detections: "رصد",
    priorityTitle: "درجة الأولوية القائمة على القواعد",
    closePanel: "إغلاق لوحة التفاصيل",
    pickPrefix: "اختر رصداً على الخريطة، أو حادثاً من القائمة، أو اضغط",
    pickSuffix: "للانتقال إلى ولاية.",
    groupingStatus: "حالة التجميع",
    priorityRule: "الأولوية — قائمة على قواعد",
    verification: "حالة التحقق",
    status: "الحالة",
    evaluated: "التقييم",
    detection: "الرصد",
    wilaya: "الولاية",
    coordinates: "الإحداثيات",
    acquired: "وقت الالتقاط",
    satellite: "القمر الصناعي",
    brightness: "السطوع Ti4",
    firmsConfidence: "ثقة FIRMS",
    state: "الحالة",
    verifying: "جارٍ التحقق…",
    runAi: "تشغيل التحقق بالذكاء الاصطناعي",
    result: "النتيجة",
    probability: "الاحتمال",
    model: "النموذج",
    threshold: "العتبة",
    calibrated: "معايَر",
    yes: "نعم",
    no: "لا",
    notCalibrated:
      "غير معايَر — هذه درجة من النموذج وليست احتمالاً فعلياً لوقوع حريق.",
    envTitle: "الظروف البيئية عند الحادث",
    envLoading: "جارٍ تحميل السياق البيئي…",
    envUnavailable: "السياق البيئي غير متاح.",
    wind: "الرياح",
    gusts: "هبّات",
    temp: "الحرارة",
    humidity: "الرطوبة",
    soil01: "التربة 0–1",
    soil39: "التربة 3–9",
    soilTemp: "حرارة التربة",
    elevation: "الارتفاع",
    soilMoisture: "رطوبة التربة",
    noteHumidity: "رطب ← · → جافّ",
    noteSoil: "عميق ← · → وقود سطحي",
    noteWind: "هادئ ← · → قوي",
    bandsOnly: "النطاقات تصف الظروف المقاسة فقط. لا درجة خطر حريق ولا حكم.",
    refreshEnv: "تحديث الظروف",
    tlLabel: "الخط الزمني",
    tlRange: "النطاق الزمني",
    tlReplayTitle:
      "إعادة عرض الرصد المسجَّل عبر الزمن. هذا تشغيل لبيانات مخزَّنة وليس توقعاً.",
    tlStop: "❚❚ إيقاف",
    tlReplay: "▶ إعادة العرض",
    tlFoot:
      "تعرض الإعادة الرصد المسجَّل خطوة بخطوة. الأوقات بالتوقيت المحلي للجزائر (UTC+1). ليست نموذج انتشار حرائق وليست توقعاً.",
    mapWilayas: "الولايات",
    mapFires: "الحرائق",
    mapLabels: "الأسماء",
    mapFailed: "فشل",
    mapStarting: "جارٍ بدء الخريطة…",
    mapLoading: "جارٍ التحميل",
    mapDrawn: "عنصراً مرسوماً",
    statWilayas: "ولاية",
    mapUnavailable: "الخريطة غير متاحة.",
    clearFilter: "إلغاء تصفية الولاية",
    filteredTo: "مصفّى إلى",
    noneInView: "لا رصد ضمن العرض",
    hasNone: "لا رصد فيها",
    noneWord: "لا شيء",
    inRange: "في النطاق المحدد.",
    loadedWiden: "محمّلة — وسّع النطاق لعرضها.",
    frpTitle: "القدرة الإشعاعية للحريق",
    historicalObs: "رصد تاريخي",
    indep: "نموذج بحثي مستقل. غير تابع لأي جهة حكومية ولا معتمد منها. ليس نموذج انتشار حرائق.",
    footer:
      "نموذج بحثي مستقل. غير تابع لأي جهة حكومية. ليس نموذج انتشار حرائق. البيانات: NASA FIRMS/VIIRS · Open-Meteo · GeoAlgeria (ODbL).",
    apiDown: "تعذّر الوصول إلى الخادم.",
    apiDownHint: "— شغّله بالأمر",
    apiDownTail: "ثم أعد تحميل الصفحة.",
    tlOnMap: "على الخريطة",
    tlInRange: "ضمن النطاق",
    tlShown: "معروضة",
    tlLoaded: "محمّلة",
    moveStart: "تحريك بداية النافذة",
    moveEnd: "تحريك نهاية النافذة",
    panWindow: "تحريك النافذة الزمنية",
    tlOnlyPre: "فقط",
    tlOnlyPost: "من الرصد محمّلة، لذا سيعرض هذا النطاق النقاط نفسها.",
    rngToday: "اليوم",
    rngTodayTitle: "من 00:00 بتوقيت الجزائر حتى الآن",
    rng24h: "24 ساعة",
    rng24hTitle: "آخر 24 ساعة متحركة حتى الآن",
    rng7d: "7 أيام",
    rng7dTitle: "آخر 7 أيام متحركة حتى الآن",
    rngAll: "الكل",
    rngAllTitle: "كل ما هو محمّل حالياً",
    noDataset: "لا توجد مجموعة بيانات، فلا تسهم بشيء:",
    envCentroid: "مركز الحادث",
    envObserved: "رُصدت",
    priorityNote:
      "priority-v1 حتمية وقائمة على قواعد. وهي ليست المدقّق بالذكاء الاصطناعي ولا تستخدم مخرجات النموذج أبداً.",
    windCapPre: "يشير السهم إلى الاتجاه الذي تهبّ الرياح",
    windTo: "نحوه",
    windCapPost: ". بينما تُبلغ Open-Meteo عن الاتجاه الذي تهبّ منه. ليس نموذج انتشار حرائق.",
    clusterSpread: "تشتّت التجمّع",
    searchNoMatchPre: "لا توجد ولاية تطابق",
    searchLoadedSuf: "ولاية محمّلة.",
    searchDet: "رصد",
    searchNoDet: "لا رصد",
    tlBarOne: "رصد",
    tlBarMany: "رصد",
    tlAt: "عند",
    attribLabel: "إسناد البيانات",
    attrDetections: "رصد الحرائق",
    attrBoundaries: "حدود الولايات",
    attrWorld: "الخطوط الخارجية للعالم",
    attrWeather: "الطقس",
    attrRenderer: "مُصيِّر الخريطة",
  },
} as const;

/* Compile-time guard: adding an English key without an Arabic one fails typecheck. */
type _ArabicMustBeComplete = { [K in keyof (typeof dict)["en"]]: string };
const _check: _ArabicMustBeComplete = dict.ar;
void _check;

export type Dict = { [K in keyof (typeof dict)["en"]]: string };

interface Ctx {
  lang: Lang;
  dir: "ltr" | "rtl";
  t: Dict;
  toggle: () => void;
}

const fallback: Ctx = { lang: "en", dir: "ltr", t: dict.en, toggle: () => {} };
const I18n = createContext<Ctx>(fallback);

function initial(): Lang {
  try {
    const saved = localStorage.getItem("numidia-lang");
    if (saved === "ar" || saved === "en") return saved;
  } catch {
    /* storage can be unavailable; fall through */
  }
  return "en";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(initial);
  const dir: "ltr" | "rtl" = lang === "ar" ? "rtl" : "ltr";

  useEffect(() => {
    /* lang only. `dir` is deliberately NOT set on <html>: direction is
       inherited, so a global flip would reverse the map and the timeline too.
       Panels that hold text opt in individually. */
    document.documentElement.lang = lang;
    try {
      localStorage.setItem("numidia-lang", lang);
    } catch {
      /* ignore */
    }
  }, [lang]);

  const toggle = useCallback(() => setLang((l) => (l === "en" ? "ar" : "en")), []);
  const value = useMemo(
    () => ({ lang, dir, t: dict[lang] as Dict, toggle }),
    [lang, dir, toggle],
  );
  return <I18n.Provider value={value}>{children}</I18n.Provider>;
}

export const useI18n = () => useContext(I18n);