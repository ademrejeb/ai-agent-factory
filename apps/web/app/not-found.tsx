import Link from "next/link";

import { Icon } from "@/components/ui/Icon";

export default function NotFound() {
  return (
    <div className="empty" style={{ paddingTop: 80 }}>
      <span className="empty-icon">
        <Icon name="search" size={22} />
      </span>
      <h3>Page not found</h3>
      <p>The page you requested does not exist, or the resource was moved.</p>
      <div className="empty-action row">
        <Link href="/" className="btn btn-primary btn-md">
          Back to overview
        </Link>
        <Link href="/agents" className="btn btn-secondary btn-md">
          Browse agents
        </Link>
      </div>
    </div>
  );
}
