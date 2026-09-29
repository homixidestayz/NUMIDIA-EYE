import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Detection, SystemStatus } from "../types";

export type Phase = "loading" | "ready" | "error";

export interface UseDetectionsResult {
  detections: Detection[];
  status: SystemStatus | null;
  /** "ready" once a detections response has been received - including [].
   *  "error" only when the detections request itself failed. */
  phase: Phase;
  /** Real failure reason (e.g. "API 503 Service Unavailable"), never invented. */
  error: string | null;
  isEmpty: boolean;
  isStale: boolean;
  refresh: () => void;
  lastUpdated: Date | null;
}

const DETECTION_LIMIT = 500;

function describe(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/**
 * Single source of truth for dashboard data.
 *
 * Fetches ONLY the real API (/system/status, /detections). There is no
 * fallback, fixture, or generated detection: when a request fails the list
 * stays empty and the error is surfaced instead.
 *
 * The two requests settle independently, so a healthy /system/status is
 * still shown when /detections fails. Every request is aborted on unmount
 * and on refresh, so a superseded response can never overwrite newer state.
 */
export function useDetections(): UseDetectionsResult {
  const [detections, setDetections] = useState<Detection[]>([]);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [nonce, setNonce] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    abortRef.current?.abort();
    abortRef.current = controller;

    let active = true;
    setPhase("loading");
    setError(null);

    // The two requests settle independently, so a healthy /system/status is
    // still shown when /detections fails. Nothing is awaited jointly.
    void api
      .status(controller.signal)
      .then((value) => {
        if (active && !controller.signal.aborted) setStatus(value);
      })
      .catch((err: unknown) => {
        if (active && !controller.signal.aborted) setError(describe(err));
      });

    void api
      .detections(DETECTION_LIMIT, controller.signal)
      .then((value) => {
        if (!active || controller.signal.aborted) return;
        setDetections(value);
        setPhase("ready");
        setLastUpdated(new Date());
      })
      .catch((err: unknown) => {
        if (!active || controller.signal.aborted) return;
        setDetections([]);
        setPhase("error");
        setError(describe(err));
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [nonce]);

  return {
    detections,
    status,
    phase,
    error,
    isEmpty: phase === "ready" && detections.length === 0,
    isStale: status?.data_state === "STALE",
    refresh,
    lastUpdated,
  };
}
