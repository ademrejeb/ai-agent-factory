"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { explainError } from "@/lib/errors";

interface ReferenceChipProps {
  code: string;
  message?: string | null;
  compact?: boolean;
}

/**
 * A code is only useful if the reader can discover what it means. The chip
 * expands inline with the explanation, so nobody has to leave the page or
 * guess whether E30 is a platform error or a business reference.
 */
export function ReferenceChip({ code, message, compact = false }: ReferenceChipProps) {
  const [open, setOpen] = useState(!compact);
  const help = explainError(code, message);
  return (
    <span className={`reference-chip reference-${help.tone}`}>
      <button
        type="button"
        className="reference-trigger"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Badge tone={help.tone === "danger" ? "danger" : help.tone === "warning" ? "warning" : "neutral"}>
          {code}
        </Badge>
        <span>{help.title}</span>
      </button>
      {open ? (
        <span className="reference-body">
          <span>
            <strong>Why: </strong>
            {help.why}
          </span>
          <span>
            <strong>What to do: </strong>
            {help.fix}
          </span>
        </span>
      ) : null}
    </span>
  );
}
