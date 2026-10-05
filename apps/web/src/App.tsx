import { useCallback, useEffect, useRef, useState } from "react";
import type { AiResult, Detection, Lang } from "./types";
import { t } from "./i18n";
import { ApiError, api } from "./api";
import { useDetections } from "./hooks/useDetections";
import { useIncidents } from "./hooks/useIncidents";
import StatusHeader from "./components/StatusHeader";
import Sidebar from "./components/Sidebar";
import DetectionMap from "./components/DetectionMap";
import IncidentPanel from "./components/IncidentPanel";
import FlowRail from "./components/FlowRail";

export type DetailPhase = "idle" | "loading" | "ready" | "missing" | "error";

export default function App() {
  const [lang, setLang] = useState<Lang>("en");
  const [detail, setDetail] = useState<Detection | null>(null);
  const [detailPhase, setDetailPhase] = useState<DetailPhase>("idle");
  const [detailStale, setDetailStale] = useState(false);
  // The real /ai response for the current selection, mirrored upward purely so
  // the operational-chain rail can show that VERIFY actually ran. The verdict
  // itself is still rendered only by AiVerification.
  const [aiResult, setAiResult] = useState<AiResult | null>(null);
  const dict = t(lang);

  // All backend data flows through this hook: /system/status + /detections
  // only, with loading / ready / error / empty states and request abort.
  const { detections, status, phase, error, isStale } = useDetections();

  // Real incident grouping + priority (/incidents) and the real incident report
  // (/incidents/{id}/report). Both fail visibly rather than substituting data.
  const {
    incidents,
    phase: incidentPhase,
    error: incidentError,
    report,
    reportPhase,
    reportError,
    openReport,
    closeReport,
  } = useIncidents();

  // Guards against an out-of-order detail response overwriting a newer
  // selection (click A then B: A must never win).
  const detailRequestId = useRef(0);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);

  // Authoritative detail always comes from GET /detections/{id}, never from
  // list-row values alone. On failure the (real) list row stays visible and
  // is explicitly marked as not the authoritative record.
  const select = useCallback(
    async (id: string | null) => {
      const requestId = ++detailRequestId.current;
      if (id === null) {
        setDetail(null);
        setDetailPhase("idle");
        setDetailStale(false);
        return;
      }
      const fallback = detections.find((d) => d.detection_id === id) ?? null;
      setDetailPhase("loading");
      try {
        const full = await api.detection(id);
        if (requestId !== detailRequestId.current) return;
        setDetail(full);
        setDetailPhase("ready");
        setDetailStale(false);
      } catch (err) {
        if (requestId !== detailRequestId.current) return;
        // Never substitute invented data: the list row is real API content,
        // and it is flagged as not authoritative.
        setDetail(fallback);
        setDetailPhase(err instanceof ApiError && err.status === 404 ? "missing" : "error");
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
      <FlowRail
        dict={dict}
        detections={detections.length}
        detectState={status?.data_state ?? dict.status_unknown}
        selectionMade={detail != null}
        detailReady={detailPhase === "ready"}
        aiServed={aiResult?.status === "available" && aiResult.probability != null}
        aiModel={aiResult?.model ?? null}
        incidentsCount={incidentPhase === "error" ? null : incidents.length}
        reportReady={reportPhase === "ready"}
      />
      <div className="main">
        <aside className="rail rail-left">
          <IncidentPanel
            dict={dict}
            incidents={incidents}
            phase={incidentPhase}
            error={incidentError}
            report={report}
            reportPhase={reportPhase}
            reportError={reportError}
            onOpenReport={openReport}
            onCloseReport={closeReport}
          />
        </aside>
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
          detailPhase={detailPhase}
          detailStale={detailStale}
          onAiResult={setAiResult}
          onSelect={(id) => void select(id)}
          onCloseDetail={() => void select(null)}
        />
      </div>
    </div>
  );
}
