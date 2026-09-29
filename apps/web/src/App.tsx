import { useCallback, useEffect, useState } from "react";
import type { Detection, Lang } from "./types";
import { t } from "./i18n";
import { api } from "./api";
import { useDetections } from "./hooks/useDetections";
import StatusHeader from "./components/StatusHeader";
import Sidebar from "./components/Sidebar";
import DetectionMap from "./components/DetectionMap";

export default function App() {
  const [lang, setLang] = useState<Lang>("en");
  const [detail, setDetail] = useState<Detection | null>(null);
  const [detailStale, setDetailStale] = useState(false);
  const dict = t(lang);

  // All backend data flows through this hook: /system/status + /detections
  // only, with loading / ready / error / empty states and request abort.
  const { detections, status, phase, error, isStale } = useDetections();

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);

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
      {phase === "error" && (
        <div className="banner banner-warn">
          {dict.load_error}
          {error ? ` (${error})` : ""}
        </div>
      )}
      {isStale && <div className="banner banner-warn">{dict.stale}</div>}
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
