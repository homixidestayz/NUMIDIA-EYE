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
  const [detail, setDetail] = useState<Detection | null>(null);
  const [detailStale, setDetailStale] = useState(false);
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

  // Authoritative detail always comes from GET /detections/{id}, never from
  // list-row values alone. On failure the list row stays visible and marked.
  const select = useCallback(
    async (id: string | null) => {
      if (id === null) {
        setDetail(null);
        setDetailStale(false);
        return;
      }
      const fallback = detections.find((d) => d.detection_id === id) ?? null;
      try {
        setDetail(await api.detection(id));
        setDetailStale(false);
      } catch {
        setDetail(fallback);
        setDetailStale(true);
      }
    },
    [detections]
  );

  return (
    <div className="app">
      <StatusHeader
        status={status}
        dict={dict}
        onToggleLang={() => setLang((p) => (p === "en" ? "ar" : "en"))}
      />
      {apiError && <div className="banner banner-warn">{apiError}</div>}
      {status?.data_state === "STALE" && (
        <div className="banner banner-warn">{dict.stale}</div>
      )}
      <div className="main">
        <DetectionMap
          detections={detections}
          lang={lang}
          dict={dict}
          detail={detail}
          detailStale={detailStale}
          onSelect={(id) => void select(id)}
        />
        <Sidebar
          status={status}
          detections={detections}
          lang={lang}
          dict={dict}
          detail={detail}
          detailStale={detailStale}
          onSelect={(id) => void select(id)}
          onCloseDetail={() => void select(null)}
        />
      </div>
    </div>
  );
}
