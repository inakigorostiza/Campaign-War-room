interface Props {
  text: string;
  streaming: boolean;
  date: string | null;
}

export default function NarrativePanel({ text, streaming, date }: Props) {
  return (
    <div className="panel narrative-panel">
      <div className="panel-title">
        Analyst Briefing
        <span className="narrative-meta">{date ?? ""}</span>
      </div>
      <div className="narrative-body">
        {text || (streaming ? "" : "Awaiting first refresh…")}
        {streaming && <span className="cursor">▍</span>}
      </div>
    </div>
  );
}
