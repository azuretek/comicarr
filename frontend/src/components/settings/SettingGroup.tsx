interface SettingGroupProps {
  title: string;
  description?: string;
  children: React.ReactNode;
}

export function SettingGroup({
  title,
  description,
  children,
}: SettingGroupProps) {
  return (
    <section className="mb-8">
      <div className="mb-4">
        <div className="text-base font-medium tracking-wide text-foreground">
          {title}
        </div>
        {description && (
          <div className="text-base text-muted-foreground leading-relaxed">
            {description}
          </div>
        )}
      </div>
      <div className="space-y-2">{children}</div>
    </section>
  );
}
