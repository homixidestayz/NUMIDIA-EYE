import type { Dict } from "../i18n";

export type StageState = "ready" | "idle" | "unavailable";

interface Stage {
  key: string;
  index: number;
  name: string;
  hint: string;
  state: StageState;
  /** Real value for this stage, or the localized idle/unavailable word. */
  value: string;
}

interface Props {
  dict: Dict;
  /** Real detection count served by the API. */
  detections: number;
  /** Real data state reported by the backend (LIVE / HISTORICAL / ...). */
  detectState: string;
  /** True when a detection is selected. */
  selectionMade: boolean;
  /** Authoritative detection detail loaded. */
  detailReady: boolean;
  /** True only when the API actually served a model result. */
  aiServed: boolean;
  /** Real model name reported by the API. */
  aiModel: string | null;
  /** Number of real incidents, or null when the request failed. */
  incidentsCount: number | null;
  /** True when a real incident report is open. */
  reportReady: boolean;
}

/**
 * DETECT -> VERIFY -> UNDERSTAND -> PRIORITIZE -> RESPOND.
 *
 * Every node reflects real state that came from the API. Nothing is pre-filled,
 * animated in, or assumed: a stage is only marked ready when the data that
 * stage needs actually exists right now, and a failed request shows
 * "unavailable" rather than a plausible-looking value.
 */
export default function FlowRail({
  dict,
  detections,
  detectState,
  selectionMade,
  detailReady,
  aiServed,
  aiModel,
  incidentsCount,
  reportReady,
}: Props) {
  const idle = dict.flow_idle;
  const select = dict.flow_select;
  const unavailable = dict.flow_unavailable;

  const stages: Stage[] = [
    {
      key: "detect",
      index: 1,
      name: dict.flow_detect,
      hint: dict.flow_hint_detect,
      state: detections > 0 ? "ready" : "idle",
      value: detections > 0 ? `${detections} · ${detectState}` : select,
    },
    {
      key: "verify",
      index: 2,
      name: dict.flow_verify,
      hint: dict.flow_hint_verify,
      state: aiServed ? "ready" : "idle",
      value: aiServed ? (aiModel ?? dict.ai_model) : selectionMade ? idle : select,
    },
    {
      key: "understand",
      index: 3,
      name: dict.flow_understand,
      hint: dict.flow_hint_understand,
      state: detailReady ? "ready" : "idle",
      value: detailReady ? dict.details : selectionMade ? idle : select,
    },
    {
      key: "prioritize",
      index: 4,
      name: dict.flow_prioritize,
      hint: dict.flow_hint_prioritize,
      state:
        incidentsCount === null
          ? "unavailable"
          : incidentsCount > 0
            ? "ready"
            : "idle",
      value:
        incidentsCount === null
          ? unavailable
          : incidentsCount > 0
            ? `${incidentsCount} ${dict.incidents_count}`
            : dict.incidents_empty,
    },
    {
      key: "respond",
      index: 5,
      name: dict.flow_respond,
      hint: dict.flow_hint_respond,
      state: reportReady ? "ready" : "idle",
      value: reportReady ? dict.report_generated : idle,
    },
  ];

  return (
    <nav className="flow" aria-label={dict.flow_title}>
      <span className="flow-title">{dict.flow_title}</span>
      <ol className="flow-track" data-testid="flow-track">
        {stages.map((stage, i) => (
          <li key={stage.key} className={`flow-node is-${stage.state}`}>
            <span className="flow-index" aria-hidden="true">
              {stage.index}
            </span>
            <span className="flow-body">
              <b className="flow-name" data-testid={`flow-${stage.key}`}>
                {stage.name}
              </b>
              <span className="flow-hint">{stage.hint}</span>
              <span className="flow-value" data-testid={`flow-${stage.key}-value`}>
                {stage.value}
              </span>
            </span>
            {i < stages.length - 1 && <span className="flow-link" aria-hidden="true" />}
          </li>
        ))}
      </ol>
    </nav>
  );
}