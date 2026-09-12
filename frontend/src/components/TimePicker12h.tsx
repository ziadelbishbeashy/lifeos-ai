import { useMemo, useState } from "react";

export function formatTime12h(value?: string | null) {
  const raw = String(value || "").trim();
  const match = /^(\d{1,2}):(\d{2})$/.exec(raw);
  if (!match) return raw;
  const hour24 = Number(match[1]);
  const minute = Number(match[2]);
  if (hour24 < 0 || hour24 > 23 || minute < 0 || minute > 59) return raw;
  const meridiem = hour24 >= 12 ? "PM" : "AM";
  const hour12 = hour24 % 12 || 12;
  return `${hour12}:${String(minute).padStart(2, "0")} ${meridiem}`;
}

function toParts(value?: string | null) {
  const raw = String(value || "").trim();
  const match = /^(\d{1,2}):(\d{2})$/.exec(raw);
  const hour24 = match ? Math.min(23, Math.max(0, Number(match[1]))) : 9;
  const rawMinute = match ? Math.min(59, Math.max(0, Number(match[2]))) : 0;
  const minute = Math.floor(rawMinute / 5) * 5;
  return {
    hour: hour24 % 12 || 12,
    minute,
    meridiem: hour24 >= 12 ? "PM" : "AM" as "AM" | "PM",
  };
}

function to24Hour(hour: number, minute: number, meridiem: "AM" | "PM") {
  let hour24 = hour % 12;
  if (meridiem === "PM") hour24 += 12;
  return `${String(hour24).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

export function TimePicker12h({
  value,
  onChange,
  allowEmpty = false,
  ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  allowEmpty?: boolean;
  ariaLabel?: string;
}) {
  const parts = useMemo(() => toParts(value), [value]);
  const minuteOptions = useMemo(() => Array.from({ length: 12 }, (_, index) => index * 5), []);
  const update = (next: Partial<typeof parts>) => {
    const merged = { ...parts, ...next };
    onChange(to24Hour(merged.hour, merged.minute, merged.meridiem));
  };

  return <div className="time-picker-12h" aria-label={ariaLabel}>
    {allowEmpty ? <button type="button" className={!value ? "time-picker-clear active" : "time-picker-clear"} onClick={() => onChange("")}>Not set</button> : null}
    <select aria-label="Hour" value={parts.hour} onChange={(event) => update({ hour: Number(event.target.value) })}>
      {Array.from({ length: 12 }, (_, index) => index + 1).map(hour => <option key={hour} value={hour}>{hour}</option>)}
    </select>
    <span className="time-picker-colon">:</span>
    <select aria-label="Minute" value={parts.minute} onChange={(event) => update({ minute: Number(event.target.value) })}>
      {minuteOptions.map(minute => <option key={minute} value={minute}>{String(minute).padStart(2, "0")}</option>)}
    </select>
    <div className="time-picker-meridiem" role="group" aria-label="AM or PM">
      {(["AM", "PM"] as const).map(item => <button type="button" key={item} className={parts.meridiem === item && value ? "active" : ""} onClick={() => update({ meridiem: item })}>{item}</button>)}
    </div>
  </div>;
}

export function TimePicker12hField({ name, defaultValue = "", allowEmpty = true, ariaLabel }: { name: string; defaultValue?: string; allowEmpty?: boolean; ariaLabel?: string }) {
  const [value, setValue] = useState(defaultValue);
  return <>
    <TimePicker12h value={value} onChange={setValue} allowEmpty={allowEmpty} ariaLabel={ariaLabel} />
    <input type="hidden" name={name} value={value} />
  </>;
}
