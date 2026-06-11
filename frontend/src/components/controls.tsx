// Shared, generic form controls reused by both the sheet OptionsPanel and the
// table TableOptionsPanel. Keep these presentational — no app/option state here.

export function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">
        {label}
      </label>
      {children}
    </div>
  );
}

export function Select({
  value,
  onChange,
  options,
  disabled,
  testId,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  disabled: boolean;
  testId?: string;
}) {
  return (
    <select
      data-testid={testId}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm bg-white disabled:bg-slate-100 disabled:text-slate-400 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function NumberInput({
  value,
  min,
  max,
  onChange,
  disabled,
  testId,
}: {
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
  disabled: boolean;
  testId?: string;
}) {
  return (
    <input
      data-testid={testId}
      type="number"
      min={min}
      max={max}
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      disabled={disabled}
      className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm disabled:bg-slate-100 disabled:text-slate-400 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
    />
  );
}

export function Checkbox({
  checked,
  onChange,
  label,
  disabled,
  testId,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  disabled: boolean;
  testId?: string;
}) {
  return (
    <label className="flex items-center gap-2 cursor-pointer">
      <input
        data-testid={testId}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
        className="w-4 h-4 accent-brand disabled:opacity-50"
      />
      <span className="text-sm text-slate-600">{label}</span>
    </label>
  );
}
