import type { ReactNode } from "react";

interface CardProps {
  id?: string;
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
}

export function Card({
  id,
  title,
  description,
  actions,
  children,
  className = "",
  padded = true,
}: CardProps) {
  return (
    <section id={id} className={`card ${className}`.trim()}>
      {title || actions ? (
        <header className="card-header">
          <div>
            {title ? <h2 className="card-title">{title}</h2> : null}
            {description ? <p className="card-description">{description}</p> : null}
          </div>
          {actions ? <div className="card-actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className={padded ? "card-body" : "card-body card-body-flush"}>{children}</div>
    </section>
  );
}
