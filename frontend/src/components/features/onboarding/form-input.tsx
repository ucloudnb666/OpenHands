interface FormInputProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: "text" | "email";
  rows?: number;
}

export function FormInput({
  id,
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  rows,
}: FormInputProps) {
  const inputId = `form-input-${id}`;
  const inputClassName =
    "w-full rounded-md border border-[#3a3a3a] bg-transparent px-4 py-2.5 text-sm text-white placeholder:text-neutral-500 focus:border-white focus:outline-none transition-colors";

  return (
    <div className="flex flex-col gap-1.5 w-full">
      <label
        htmlFor={inputId}
        className="text-sm font-medium text-neutral-400 cursor-pointer"
      >
        {label}
      </label>
      {rows ? (
        <textarea
          id={inputId}
          data-testid={inputId}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          rows={rows}
          className={`${inputClassName} resize-none`}
        />
      ) : (
        <input
          id={inputId}
          data-testid={inputId}
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className={inputClassName}
        />
      )}
    </div>
  );
}
