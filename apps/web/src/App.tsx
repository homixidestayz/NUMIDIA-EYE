import { useCallback, useEffect, useState } from "react";
import type { Detection, Lang, SystemStatus } from "./types";
import { t } from "./i18n";
import { api } from "./api";
import StatusHeader from "./components/StatusHeader";
import Sidebar from "./components/Sidebar";
import DetectionMap from "./components/DetectionMap";

export default function App() {
  const [lang, setLang] = useState<Lang>("en");
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [apiError, setApiError] = useState<string | null>(null);
  const dict = t(lang);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);

  const load = useCallback(async () => {
    try {
      const [s, d] = await Promise.all([api.status(), api.detections(500)]);
      setStatus(s);
      setDetections(d);
      setApiError(null);
    } catch {
      setStatus(null);
      setDetections([]);
      setApiError(dict.load_error);
    }
  }, [dict]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="app">
      <StatusHeader
        status={status}
        lang={lang}
        dict={dict}
        onToggleLang={() => setLang((p) => (p === "en" ? "ar" : "en"))}
      />
      {apiError && <div className="banner banner-warn">{apiError}</div>}
      <div className="main">
        <DetectionMap detections={detections} lang={lang} dict={dict} />
        <Sidebar status={status} detections={detections} lang={lang} dict={dict} />
      </div>
    </div>
  );
}