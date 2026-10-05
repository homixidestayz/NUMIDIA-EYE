import { useCallback, useEffect, useRef, useState } from "react";
import { Brain } from "lucide-react";
import { api } from "../api";
import type { AiResult } from "../types";
import type { Dict } from "../i18n";

interface Props {
  detectionId: string | null;
  dict: Dict;
  /**
   * Optional: reports the real API result (or null when cleared) so the
   * operational-chain rail can reflect VERIFY without duplicating the request.
   */
  onResult?: (result: AiResult | null) => void;
}

type Phase = "idle" | "loading" | "done";

/**
 * AI VERIFICATION against the real backend.
 *
 * One click -> GET /detections/{id}/ai -> real model inference -> real verdict.
 * Nothing here is fabricated: no Math.random, no hard-coded probability, no
 * placeholder verdict. The panel renders ONLY what the API returned, and when
 * the API declines (503 AI_UNAVAILABLE) it says so instead of inventing a
 * result.
 */
export default function AiVerification({ detectionId, dict, onResult }: Props) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<AiResult | null>(null);

  // Guards an out-of-order response from overwriting a newer click.
  const requestId = useRef(0);

  // The rail only ever sees the real API result, and only for the detection
  // currently selected. Changing selection clears the previous verdict so a
  // stale model output is never presented as if it belonged to a new row.
  useEffect(() => {
    setResult(null);
    setPhase("idle");
    onResult?.(null);
  }, [detectionId, onResult]);

  const run = useCallback(async () => {
    if (!detectionId) return;
    const id = ++requestId.current;
    setPhase("loading");
    setResult(null);
    onResult?.(null);
    try {
      const res = await api.ai(detectionId);
      if (id !== requestId.current) return;
      setResult(res);
      setPhase("done");
      onResult?.(res);
    } catch (err) {
      if (id !== requestId.current) return;
      // A transport failure is reported as a failure, never as a verdict.
      const failed: AiResult = {
        status: "REQUEST_FAILED",
        message: err instanceof Error ? err.message : String(err),
      };
      setResult(failed);
      setPhase("done");
      onResult?.(failed);
    }
  }, [detectionId, onResult]);

  if (!detectionId) return null;

  const served = result?.status === "available" && result.probability != null;

  return (
    <div className="ai-panel">
      <div className="row">
        <button className="lang-btn" onClick={() => void run()} disabled={phase === "loading"}>
          <Brain size={14} /> {phase === "loading" ? dict.ai_verifying : dict.ai_verify}
        </button>
      </div>

      {phase === "done" && result && (
        <div className="ai-result" data-testid="ai-result">
          <div className="row small">
            <span>{dict.ai_verification}</span>
            <b>{dict.ai_experimental}</b>
          </div>

          {served ? (
            <>
              <div className="row">
                <span>{dict.ai_model}</span>
                <span>{result.model ?? dict.field_unavailable}</span>
              </div>
              <div className="row">
                <span>{dict.ai_result}</span>
                <b data-testid="ai-prediction">{result.prediction ?? dict.field_unavailable}</b>
              </div>
              <div className="row">
                <span>{dict.ai_probability}</span>
                <span data-testid="ai-probability">
                  {(result.probability as number).toFixed(4)}
                </span>
              </div>
              <div className="row small">
                <span>{dict.ai_threshold}</span>
                <span>
                  {typeof result.threshold === "number"
                    ? result.threshold.toFixed(4)
                    : dict.field_unavailable}
                </span>
              </div>
              <div className="row small">
                <span>{dict.ai_schema}</span>
                <span>{result.features_schema ?? dict.field_unavailable}</span>
              </div>
            </>
          ) : (
            <div className="row small">
              <span>{dict.ai_unavailable_result}</span>
            </div>
          )}
          <div className="row small">
            <span>{dict.ai_scope}</span>
          </div>
        </div>
      )}
    </div>
  );
}