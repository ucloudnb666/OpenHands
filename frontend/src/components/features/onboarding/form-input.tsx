export const isValidEmail = (email: string): boolean =>
  /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$/.test(
    email,
  );

interface FormInputProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: "text" | "email";
  rows?: number;
  required?: boolean;
  showError?: boolean;
}

export function FormInput({
  id,
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  rows,
  required = false,
  showError = false,
}: FormInputProps) {
  const inputId = `form-input-${id}`;
  const isEmailInvalid =
    type === "email" && !!value.trim() && !isValidEmail(value.trim());
  const hasError = showError && ((required && !value.trim()) || isEmailInvalid);
  const inputClassName = `w-full min-h-10 rounded border bg-[#050505] px-3 py-2 text-sm leading-5 text-white placeholder:text-[#8C8C8C] placeholder:leading-5 focus:outline-none transition-colors ${
    hasError
      ? "border-red-500 focus:border-red-500"
      : "border-[#242424] focus:border-white"
  }`;

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
          required={required}
          aria-required={required}
          aria-invalid={hasError}
          aria-label={label}
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
          required={required}
          aria-required={required}
          aria-invalid={hasError}
          aria-label={label}
          className={inputClassName}
        />
      )}
    </div>
  );
}
