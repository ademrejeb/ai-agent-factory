"use client";

import { useEffect, useState } from "react";

import { Icon } from "@/components/ui/Icon";

export function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(timer);
  }, [copied]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      // Clipboard access can be denied; the value stays selectable in the UI.
      setCopied(false);
    }
  }

  return (
    <button type="button" className="btn btn-secondary btn-sm" onClick={copy}>
      <Icon name={copied ? "check" : "copy"} size={15} />
      <span>{copied ? "Copied" : label}</span>
    </button>
  );
}

export function CodeBlock({ code, language }: { code: string; language?: string }) {
  return (
    <div className="code-block">
      <div className="code-block-bar">
        <span>{language ?? "bash"}</span>
        <CopyButton value={code} />
      </div>
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  );
}
