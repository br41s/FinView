"use client";

export function LoadingDots({
  text = "Cargando datos",
  className = "",
}: Readonly<{ text?: string; className?: string }>) {
  return (
    <div
      className={`flex items-center justify-center gap-1 text-muted-foreground ${className}`}
    >
      <span className="text-sm">{text}</span>
      <span className="flex gap-0.5">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:0ms]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:150ms]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:300ms]" />
      </span>
    </div>
  );
}
