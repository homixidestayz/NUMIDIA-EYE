import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { IncidentReport, IncidentSummary } from "../types";

export type IncidentsPhase = "loading" | "ready" | "error";

export interface UseIncidentsResult {
  incidents: IncidentSummary[];
  phase: IncidentsPhase;
  /** Real failure reason, never invented. */
  error: string | null;
  /** Real methodology string reported by the backend (incident-v1 + priority-v1). */
  methodology: Record<string, unknown> | null;
  report: IncidentReport | null;
  reportPhase: "idle" | "loading" | "ready" | "error";
  reportError: string | null;
  openReport: (id: string) => void;
  closeReport: () => void;
  refresh: () => void;
}

const INCIDENT_LIMIT = 60;

/**
 * Real incident grouping + priority from GET /incidents, and the real incident
 * report from GET /incidents/{id}/report.
 *
 * Nothing here is generated locally: there is no fallback list, no synthesized
 * priority and no placeholder report. A failed request yields an empty list and
 * a visible error, which is the honest state.
 */
export function useIncidents(): UseIncidentsResult {
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [phase, setPhase] = useState<IncidentsPhase>("loading");
  const [error, setError] = useState<string | null>(null);
  const [methodology, setMethodology] = useState<Record<string, unknown> | null>(null);
  const [report, setReport] = useState<IncidentReport | null>(null);
  const [reportPhase, setReportPhase] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [reportError, setReportError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const abortRef = useRef<AbortController | null>(null);
  const reportAbortRef = useRef<AbortController | null>(null);
  const reportRequestId = useRef(0);

  useEffect(() => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setPhase("loading");
    setError(null);

    api
      .incidents(INCIDENT_LIMIT, ctrl.signal)
      .then((res) => {
        if (ctrl.signal.aborted) return;
        setIncidents(res.incidents ?? []);
        setMethodology(res.methodology ?? null);
        setPhase("ready");
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        setIncidents([]);
        setError(err instanceof Error ? err.message : String(err));
        setPhase("error");
      });

    return () => ctrl.abort();
  }, [nonce]);

  // A superseded report response must never overwrite a newer selection.
  const openReport = useCallback((id: string) => {
    reportAbortRef.current?.abort();
    const ctrl = new AbortController();
    reportAbortRef.current = ctrl;
    const requestId = ++reportRequestId.current;
    setReportPhase("loading");
    setReportError(null);
    setReport(null);
    api
      .incidentReport(id, ctrl.signal)
      .then((res) => {
        if (ctrl.signal.aborted || requestId !== reportRequestId.current) return;
        setReport(res);
        setReportPhase("ready");
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted || requestId !== reportRequestId.current) return;
        setReportError(err instanceof Error ? err.message : String(err));
        setReportPhase("error");
      });
  }, []);

  const closeReport = useCallback(() => {
    reportAbortRef.current?.abort();
    reportRequestId.current++;
    setReport(null);
    setReportError(null);
    setReportPhase("idle");
  }, []);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  return {
    incidents,
    phase,
    error,
    methodology,
    report,
    reportPhase,
    reportError,
    openReport,
    closeReport,
    refresh,
  };
}