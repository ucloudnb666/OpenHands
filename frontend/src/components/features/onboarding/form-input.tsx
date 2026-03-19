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
    "w-full min-h-10 rounded border border-[#242424] bg-[#050505] px-3 py-2 text-sm leading-5 text-white placeholder:text-[#8C8C8C] placeholder:leading-5 focus:border-white focus:outline-none transition-colors";

  return (
    <div className="flex flex-col gap-1.5 w-full">
      <label
        htmlFor={inputId}
        className="text-sm font-medium leading-5 text-[#FAFAFA] cursor-pointer"
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
          className={`${inputClassName} h-auto resize-none`}
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
